"""Editorial pass runner: prompt, call, validate, repair-retry,
fail closed (invariant 2).

This module never writes. It returns either a validated delta or a
refusal with the reason attached — the reconciler is the only thing that
touches canon, and it accepts nothing but a validated delta.

Failure policy (specs.md §12):
1. Invalid JSON or a schema violation gets ONE repair prompt quoting the
   validation error, up to `editorial.max_repair_attempts`.
2. Still invalid, or no route answered: fail closed. The chapter stays
   `editorial-pending`, nothing is appended, and the reason says which
   of the two happened.

A schema failure is a PERMANENT failure and must not walk the fallback
chain (invariant 3): the repair goes back to the same editor route with
a better prompt, it does not spend a second provider's quota on a model
that answered fine and was simply wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from novel_engine.core.config import BookConfig, GenerationParams, ModelRoute
from novel_engine.core.context_builder import (
    fill_template,
    parse_facts,
    select_facts,
)
from novel_engine.core.errors import ContextError, EditorialError
from novel_engine.core.outline import ChapterEntry
from novel_engine.editorial.schema import EditorialDelta, parse_delta
from novel_engine.providers.base import Outcome, Provider, Success
from novel_engine.providers.router import AttemptCallback, Router
from novel_engine.quality.continuity_entities import (
    find_entity_conflicts,
    render_entity_conflicts,
)
from novel_engine.quality.continuity_numbers import (
    find_number_conflicts,
    render_conflicts,
)
from novel_engine.quality.style_checks import StyleReport, build_report

#: Low temperature for a judgement task. Not a creative constant
#: (decision #22): the deliverable here is a JSON verdict, and the book's
#: drafting temperature exists to make prose less predictable.
EDITORIAL_PARAMS = GenerationParams(temperature=0.2, top_p=0.95)

#: How much of a rejected response to quote back in the repair prompt.
#: Enough to locate the mistake, not enough to double the prompt.
REPAIR_ECHO_CHARS = 4000


@dataclass
class EditorialResult:
    """What the pass produced. `delta` is None unless status is 'validated'."""

    chapter_number: int
    status: str  # "validated" | "editorial-pending"
    delta: EditorialDelta | None = None
    reason: str = ""
    repair_rounds: int = 0
    assigned_model: str = ""
    actual_model: str = ""
    fallback_triggered: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


def editorial_template() -> str:
    """The engine-owned editorial prompt (decision #26).

    Packaged, not per-book: the editorial prompt is a JSON contract plus
    assembled evidence, and a book-local edit could break the contract
    silently — spending every repair attempt and both editor routes'
    quota before failing closed.
    """
    source = resources.files("novel_engine") / "templates" / "editorial-prompt.md"
    return source.read_text(encoding="utf-8")


def style_evidence(report: StyleReport) -> str:
    """The Phase 4 numbers, rendered for a model rather than a terminal.

    Handed over as evidence precisely so the editorial pass does not
    re-derive what a regex already knows (specs §12).
    """
    metrics = report.metrics
    lines = [
        f"- word count: {metrics.word_count}"
        + (f" (target {metrics.target_words})" if metrics.target_words else ""),
        f"- sentence length: mean {metrics.sentence_length_mean:.1f}, "
        f"stdev {metrics.sentence_length_stdev:.1f}",
        f"- dialogue ratio: {metrics.dialogue_ratio:.3f}",
        f"- adverbs per 1000 words: {metrics.adverb_rate_per_1000:.1f}",
        f"- paragraphs: {metrics.paragraph_count}, "
        f"longest {metrics.paragraph_length_max} words",
    ]
    hits = {phrase: n for phrase, n in metrics.banned_phrase_hits.items() if n}
    lines.append(
        "- banned phrases used: "
        + (", ".join(f"{phrase} ({n})" for phrase, n in sorted(hits.items())) or "none")
    )
    if report.flagged:
        lines.append(
            "- outside the book's declared bands: "
            + ", ".join(
                f"{verdict.metric} {verdict.status}" for verdict in report.flagged
            )
        )
    elif report.thresholds_present:
        lines.append("- every declared style band was met")
    else:
        lines.append("- this book declares no style bands, so nothing was judged")
    return "\n".join(lines)


def build_editorial_prompt(
    book: BookConfig,
    entry: ChapterEntry,
    chapter_body: str,
) -> str:
    """Assemble the editorial prompt for one already-drafted chapter.

    Reads only. Same retrieval rule as drafting (decision #14): the
    editor sees the facts that touch this scene, not the whole ledger.
    """
    root = book.root
    character_entry = book.characters.get(entry.pov)
    if character_entry is None:
        raise ContextError(
            f"Manifest POV {entry.pov!r} has no entry in characters/index.yaml."
        )

    def read(relative: str) -> str:
        path = root / relative
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContextError(f"Cannot read {path}: {exc}") from exc

    style_guide_text = read("canon/style-guide.md")
    tracker_text = read("canon/continuity-tracker.md")
    threads_text = read("canon/open-threads.md")
    character_sheet_text = read(f"characters/{character_entry.file}")

    facts = parse_facts(tracker_text, root / "canon/continuity-tracker.md")
    selected = select_facts(
        facts,
        pov_id=entry.pov,
        beat_text=entry.beat,
        known_character_ids=list(book.characters),
        limit=book.pipeline.context.max_locked_facts,
    )

    report = build_report(
        book.slug, entry.chapter_number, chapter_body, style_guide_text
    )

    threads_block = "\n".join(
        line for line in threads_text.splitlines() if line.strip().startswith("- `[T-")
    )

    values = {
        "chapter_number": str(entry.chapter_number),
        "locked_facts": (
            "\n".join(fact.raw for fact in selected)
            or "(No locked facts touch this scene.)"
        ),
        "open_threads": threads_block or "(No threads are open.)",
        "pov_character": entry.pov,
        "beat": entry.beat,
        "character_sheet": character_sheet_text.strip(),
        "style_guide": style_guide_text.strip(),
        "style_evidence": style_evidence(report),
        "number_findings": render_conflicts(
            find_number_conflicts(selected, chapter_body)
        ),
        "entity_findings": render_entity_conflicts(
            find_entity_conflicts(selected, chapter_body, list(book.characters))
        ),
        "chapter_text": chapter_body.strip(),
    }
    return fill_template(
        editorial_template(), values, Path("templates/editorial-prompt.md")
    )


def _label(route: ModelRoute) -> str:
    return f"{route.provider}:{route.model}"


def repair_prompt(base_prompt: str, response: str, error: str) -> str:
    """Re-ask with the validation error quoted (specs §12 failure policy)."""
    return (
        f"{base_prompt}\n\n"
        "# Your previous answer was rejected\n\n"
        "It did not validate against the contract above:\n\n"
        f"{error}\n\n"
        "This is what you returned:\n\n"
        f"{response[:REPAIR_ECHO_CHARS]}\n\n"
        "Return the corrected JSON object only. No prose, no fence, no "
        "keys that are not in the contract."
    )


def run_editorial_pass(
    book: BookConfig,
    entry: ChapterEntry,
    chapter_body: str,
    providers: dict[str, Provider],
    *,
    on_attempt: AttemptCallback | None = None,
) -> EditorialResult:
    """Review one chapter and return a validated delta, or refuse.

    Never raises for a model outcome and never writes: a failure comes
    back as status 'editorial-pending' with a reason, so the caller can
    record it and leave canon untouched (invariant 2).
    """
    routes = [book.models.editor_model.primary, book.models.editor_model.fallback]
    assigned = _label(routes[0])
    served: list[ModelRoute] = []

    def capture(route: ModelRoute, outcome: Outcome, latency_ms: int) -> None:
        if isinstance(outcome, Success):
            served.append(route)
        if on_attempt is not None:
            on_attempt(route, outcome, latency_ms)

    router = Router(
        providers,
        routes,
        book.pipeline.retry,
        EDITORIAL_PARAMS,
        on_attempt=capture,
    )

    base_prompt = build_editorial_prompt(book, entry, chapter_body)
    prompt = base_prompt
    result = EditorialResult(
        chapter_number=entry.chapter_number,
        status="editorial-pending",
        assigned_model=assigned,
    )

    for round_index in range(book.pipeline.editorial.max_repair_attempts + 1):
        outcome = router.generate(prompt, json_mode=True)
        if not isinstance(outcome, Success):
            result.reason = (
                f"No editor route answered: {outcome.message[:300]}. Canon is "
                "untouched; re-run the editorial pass when providers recover."
            )
            return result

        result.repair_rounds = round_index
        result.actual_model = _label(served[-1]) if served else assigned
        result.fallback_triggered = result.actual_model != assigned
        result.input_tokens += outcome.input_tokens
        result.output_tokens += outcome.output_tokens

        try:
            delta = parse_delta(outcome.content, chapter_number=entry.chapter_number)
        except EditorialError as exc:
            result.reason = str(exc)
            # Repair from the BASE prompt, never from the last repair
            # prompt: compounding them would re-send every rejected
            # answer, and the budget is the point of failing closed fast.
            prompt = repair_prompt(base_prompt, outcome.content, str(exc))
            continue

        result.status = "validated"
        result.delta = delta
        result.reason = ""
        return result

    attempts = book.pipeline.editorial.max_repair_attempts
    result.reason = (
        f"Editor response still invalid after {attempts} repair "
        f"attempt(s). Last error:\n{result.reason}\n"
        "Failing closed: the chapter stays editorial-pending and nothing "
        "was appended to canon."
    )
    return result
