"""One chapter plus the continuation loop. Implemented in Phase 3.

The loop is load-bearing, not cosmetic (pitfall C5 / OQ-06): free-tier
models routinely undershoot the word target, so a short draft triggers a
continuation round that re-sends the full prompt plus the partial draft,
hard-capped at `max_continuation_rounds`.

Terminal case (ADR-0005): when every route is exhausted — including a
permanent failure, which short-circuits the chain — we still write a
clearly-marked failed-stub chapter locally at zero further cost. The
manifest stays `planned`; re-running with --force replaces the stub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from novel_engine.core.config import BookConfig
from novel_engine.core.errors import VaultError
from novel_engine.core.outline import ChapterEntry
from novel_engine.core.vault import flip_manifest_status, write_chapter
from novel_engine.drafting.provenance import (
    chapter_frontmatter,
    make_session_id,
    utc_timestamp,
)
from novel_engine.providers.audit import outcome_name
from novel_engine.providers.base import Outcome, Provider, Success
from novel_engine.providers.router import AttemptCallback, Router

STUB_MARKER = "FAILED-STUB"


@dataclass(frozen=True)
class AttemptRecord:
    """One model call attempt — enough for the CLI report and the audit."""

    provider: str
    model_id: str
    outcome: str
    message: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class DraftResult:
    chapter_number: int
    status: str  # "draft" | "failed-stub"
    path: Path | None
    assigned_model: str = ""
    actual_model: str = ""
    fallback_triggered: bool = False
    continuation_rounds: int = 0
    actual_words: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    session_id: str = ""
    attempts: list[AttemptRecord] = field(default_factory=list)


def word_count(text: str) -> int:
    return len(text.split())


def continuation_prompt(base_prompt: str, partial_draft: str) -> str:
    """Full context again (providers are stateless) plus the partial draft."""
    return (
        f"{base_prompt}\n\n"
        "# Partial Draft So Far\n\n"
        f"{partial_draft}\n\n"
        "The draft above is incomplete. Continue EXACTLY where it stops — "
        "do not repeat earlier text, do not summarise, do not restart, do "
        "not conclude early. Pick up mid-scene and keep writing until the "
        "chapter is complete."
    )


def _routes_for(book: BookConfig, entry: ChapterEntry):
    character = book.characters.get(entry.pov)
    if character is None or character.model not in book.models.pov_models:
        raise VaultError(
            f"No models.yaml route for POV {entry.pov!r}; cannot build the "
            "drafting chain."
        )
    pov_route = book.models.pov_models[character.model]
    return [pov_route, *book.models.fallback_chain]


def _route_label(route) -> str:
    return f"{route.provider}:{route.model}"


@dataclass
class _RoundState:
    success_routes: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


def draft_chapter(
    book: BookConfig,
    entry: ChapterEntry,
    prompt_text: str,
    providers: dict[str, Provider],
    *,
    session_id: str | None = None,
    allow_overwrite: bool = False,
    on_attempt: AttemptCallback | None = None,
) -> DraftResult:
    """Draft one chapter end-to-end and write it through core/vault.py.

    Returns data; every disk write goes through the vault primitives.
    Raises only for vault-level refusals (existing chapter without
    allow_overwrite); all API outcomes are handled, never raised.
    """
    session_id = session_id or make_session_id()
    routes = _routes_for(book, entry)
    assigned = _route_label(routes[0])
    retry = book.pipeline.retry

    records: list[AttemptRecord] = []
    state = _RoundState()

    def observe(route, outcome: Outcome, latency_ms: int) -> None:
        message = getattr(outcome, "message", "")
        records.append(
            AttemptRecord(
                provider=route.provider,
                model_id=route.model,
                outcome=outcome_name(outcome),
                message=message,
                latency_ms=latency_ms,
                input_tokens=getattr(outcome, "input_tokens", 0),
                output_tokens=getattr(outcome, "output_tokens", 0),
            )
        )
        if isinstance(outcome, Success):
            state.success_routes.append(route)
            state.input_tokens += outcome.input_tokens
            state.output_tokens += outcome.output_tokens
        if on_attempt is not None:
            on_attempt(route, outcome, latency_ms)

    router = Router(
        providers,
        routes,
        retry,
        book.models.generation_params,
        on_attempt=observe,
    )

    low_water = book.pipeline.target_words - round(
        book.pipeline.target_words * book.pipeline.word_tolerance
    )
    max_rounds = book.pipeline.max_continuation_rounds

    pieces: list[str] = []
    rounds = 0
    prompt = prompt_text
    last_outcome: Outcome | None = None

    while True:
        outcome = router.generate(prompt)
        last_outcome = outcome
        if not isinstance(outcome, Success):
            break
        pieces.append(outcome.content)
        current = "\n".join(pieces).strip()
        if word_count(current) >= low_water or rounds >= max_rounds:
            break
        rounds += 1
        prompt = continuation_prompt(prompt_text, current)

    if isinstance(last_outcome, Success):
        return _write_success(
            book,
            entry,
            pieces,
            rounds,
            assigned,
            state,
            session_id,
            allow_overwrite,
            records,
        )

    assert last_outcome is not None  # the while loop always runs once
    return _write_failed_stub(
        book,
        entry,
        assigned,
        last_outcome,
        session_id,
        allow_overwrite,
        records,
    )


def _write_success(
    book: BookConfig,
    entry: ChapterEntry,
    pieces: list[str],
    rounds: int,
    assigned: str,
    state: _RoundState,
    session_id: str,
    allow_overwrite: bool,
    records: list[AttemptRecord],
) -> DraftResult:
    body = "\n".join(piece.strip() for piece in pieces).strip() + "\n"
    actual = _route_label(state.success_routes[-1])
    fallback = any(_route_label(route) != assigned for route in state.success_routes)

    fields = chapter_frontmatter(
        chapter_number=entry.chapter_number,
        book_slug=book.slug,
        pov=entry.pov,
        arc=entry.arc,
        status="draft",
        session_id=session_id,
        created_at=utc_timestamp(),
        target_words=book.pipeline.target_words,
        actual_words=word_count(body),
        assigned_model=assigned,
        actual_model=actual,
        fallback_triggered=fallback,
        continuation_rounds=rounds,
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
    )
    path = write_chapter(
        book.root,
        entry.chapter_number,
        fields,
        body,
        allow_overwrite=allow_overwrite,
    )

    # Manifest bookkeeping: flip planned→written for a first-time draft.
    # A --force regeneration keeps whatever status the chapter already has.
    if entry.status == "planned":
        flip_manifest_status(
            book.root, entry.chapter_number, "written", expected_current="planned"
        )

    return DraftResult(
        chapter_number=entry.chapter_number,
        status="draft",
        path=path,
        assigned_model=assigned,
        actual_model=actual,
        fallback_triggered=fallback,
        continuation_rounds=rounds,
        actual_words=word_count(body),
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
        session_id=session_id,
        attempts=records,
    )


def _write_failed_stub(
    book: BookConfig,
    entry: ChapterEntry,
    assigned: str,
    failure: Outcome,
    session_id: str,
    allow_overwrite: bool,
    records: list[AttemptRecord],
) -> DraftResult:
    """ADR-0005: all routes exhausted → zero-cost marked stub, manifest
    stays planned. Re-running with --force replaces the stub."""
    last = records[-1] if records else None
    detail = (
        f"{last.provider}:{last.model_id} -> {last.outcome}: {last.message}"
        if last
        else f"{outcome_name(failure)}: {getattr(failure, 'message', '')}"
    )
    body = (
        f"> {STUB_MARKER} — chapter {entry.chapter_number} was NOT generated.\n"
        ">\n"
        "> Every model route failed (ADR-0005). This file exists so the\n"
        "> failed session is visible on disk and resumable; it is not canon\n"
        "> prose. Re-run with --force once providers recover to replace it.\n"
        ">\n"
        f"> Last error: {detail}\n"
    )
    fields = chapter_frontmatter(
        chapter_number=entry.chapter_number,
        book_slug=book.slug,
        pov=entry.pov,
        arc=entry.arc,
        status="failed-stub",
        session_id=session_id,
        created_at=utc_timestamp(),
        target_words=book.pipeline.target_words,
        actual_words=0,
        assigned_model=assigned,
        actual_model="",
        fallback_triggered=False,
        continuation_rounds=0,
        input_tokens=0,
        output_tokens=0,
    )
    path = write_chapter(
        book.root,
        entry.chapter_number,
        fields,
        body,
        allow_overwrite=allow_overwrite,
    )
    return DraftResult(
        chapter_number=entry.chapter_number,
        status="failed-stub",
        path=path,
        assigned_model=assigned,
        session_id=session_id,
        attempts=records,
    )
