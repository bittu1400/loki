"""Editorial pass against fakes: prompt assembly, the repair loop, and
failing closed. No network, and — asserted below — no writes.

The pass_runner is the component that talks to a model about canon. It
is allowed to come back empty-handed; it is not allowed to come back
with something half-valid, and it is not allowed to touch the vault."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from fakes import FakeProvider, reset_fixture_state
from novel_engine.core.config import load_book_config
from novel_engine.editorial.pass_runner import (
    EDITORIAL_PARAMS,
    build_editorial_prompt,
    editorial_template,
    run_editorial_pass,
)
from novel_engine.editorial.schema import parse_delta
from novel_engine.providers.base import (
    PermanentFailure,
    RateLimited,
    Success,
    TransientFailure,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
FAKE_ENV = {
    key: f"test-{key}"
    for key in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
        "AIHUBMIX_API_KEY",
    )
}

DELTA = {
    "chapter_number": 3,
    "continuity_violations": [
        {
            "severity": "critical",
            "violated_fact": "The spring-tide page carries two corrections.",
            "chapter_excerpt": "nine corrections on the spring-tide page",
            "explanation": "Contradicts a locked fact from ch-001.",
        }
    ],
    "new_locked_facts": [
        {
            "category": "character",
            "entity": "ovist-rhoam",
            "fact": "Ovist counts driftglass by weight.",
            "source_chapter": 3,
        }
    ],
    "thread_updates": {
        "opened": [{"text": "Someone reset the ebb ledge."}],
        "progressed": [],
        "resolved": [{"thread_id": "T-002", "resolved_in_chapter": 3}],
    },
    "chapter_summary": "Ovist walked the ledge and read the seal.",
    "next_step_note": "Sela has not been told.",
    "deepen_questions": ["Who issues the lead seals?"],
    "suggested_canon_patches": [],
    "beat_adherence": {"hit": True, "notes": "The beat lands."},
}


@pytest.fixture
def book(tmp_path: Path):
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    reset_fixture_state(copied)
    config = load_book_config(copied.parent, "example-book", env=FAKE_ENV)
    pipeline = config.pipeline.model_copy(
        update={
            "retry": config.pipeline.retry.model_copy(
                update={"max_attempts": 1, "base_delay_seconds": 0, "jitter": False}
            )
        }
    )
    object.__setattr__(config, "pipeline", pipeline)
    return config


@pytest.fixture
def entry(book):
    return next(e for e in book.manifest if e.chapter_number == 3)


BODY = (
    "Ovist counted the glass by weight. The ledge was wet.\n\n"
    '"You are late," Sela said.\n\nHe did not answer.\n'
)


def editor_providers(*outcomes, fallback=None):
    """mistral primary, gemini fallback — the fixture's editor routes
    since decision #28."""
    return {
        "mistral": FakeProvider(*outcomes),
        "gemini": FakeProvider(fallback or RateLimited("unused")),
    }


def ok(payload, model="mistral-medium-latest") -> Success:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return Success(text, model, 800, 200, 40)


def canon_digest(book) -> str:
    """One hash over every file the reconciler may later touch."""
    digest = hashlib.sha256()
    for relative in (
        "canon/continuity-tracker.md",
        "canon/open-threads.md",
        "canon/deepen-queue.md",
        "log/chapter-summary.md",
    ):
        digest.update((book.root / relative).read_bytes())
    return digest.hexdigest()


# --- prompt assembly --------------------------------------------------------


def test_prompt_carries_the_evidence_and_leaves_no_slot_unfilled(book, entry) -> None:
    prompt = build_editorial_prompt(book, entry, BODY)

    assert "{{" not in prompt
    assert "Ovist counted the glass by weight." in prompt  # the chapter
    assert entry.beat in prompt  # what it was commissioned to do
    assert "`[character:ovist-rhoam]`" in prompt  # retrieved locked facts
    assert "- `[T-002]` `[open]`" in prompt  # open threads, for real ids
    assert "word count: 19" in prompt  # Phase 4 numbers, pre-computed
    assert "dialogue ratio:" in prompt


def test_prompt_carries_the_deterministic_number_findings(book, entry) -> None:
    """Decision #30: the check runs before the call, and its result is
    in the prompt either way — a 'nothing disagreed' line is evidence
    too, and stops the model treating silence as absence of the check."""
    clean = build_editorial_prompt(book, entry, BODY)
    assert "## Number checks" in clean
    assert "no quantity in the chapter disagrees" in clean

    contradicting = build_editorial_prompt(
        book,
        entry,
        "Nine corrections on the spring-tide page, nine countersignings "
        "that pointed to a clerk dead six years.\n",
    )
    assert "canon says 2, the chapter says 9" in contradicting


def test_prompt_retrieves_facts_rather_than_dumping_the_ledger(book, entry) -> None:
    tracker = (book.root / "canon/continuity-tracker.md").read_text(encoding="utf-8")
    all_facts = [line for line in tracker.splitlines() if line.startswith("- `[")]
    prompt = build_editorial_prompt(book, entry, BODY)
    included = [line for line in all_facts if line in prompt]

    assert included, "retrieval returned nothing at all"
    assert len(included) < len(all_facts), "the whole ledger was dumped (pitfall A3)"


def test_the_templates_example_is_itself_a_valid_delta() -> None:
    """Anti-drift: the shape the model is shown must be the shape the
    schema accepts, or every session pays repair attempts to find out."""
    fence = re.search(r"```json\n(.*?)\n```", editorial_template(), re.DOTALL)
    assert fence, "the template no longer shows an example object"
    parse_delta(fence.group(1))


# --- the call ---------------------------------------------------------------


def test_valid_response_is_returned_as_a_delta(book, entry) -> None:
    result = run_editorial_pass(book, entry, BODY, editor_providers(ok(DELTA)))

    assert result.status == "validated"
    assert result.repair_rounds == 0
    assert result.delta is not None
    assert result.delta.thread_updates.resolved[0].thread_id == "T-002"
    assert result.actual_model == "mistral:mistral-medium-latest"
    assert result.fallback_triggered is False
    assert result.reason == ""


def test_the_pass_asks_for_json_at_a_judgement_temperature(book, entry) -> None:
    providers = editor_providers(ok(DELTA))
    run_editorial_pass(book, entry, BODY, providers)

    request = providers["mistral"].calls[0]
    assert request.json_mode is True
    assert request.temperature == EDITORIAL_PARAMS.temperature == 0.2
    assert book.models.generation_params.temperature == 0.9  # drafting is untouched


def test_prose_wrapped_json_is_repaired_then_accepted(book, entry) -> None:
    providers = editor_providers(
        ok("Here is my review:\n\n" + json.dumps(DELTA)),
        ok(DELTA),
    )
    result = run_editorial_pass(book, entry, BODY, providers)

    assert result.status == "validated"
    assert result.repair_rounds == 1
    repair = providers["mistral"].calls[1].prompt
    assert "Your previous answer was rejected" in repair
    assert "not valid JSON" in repair
    assert result.input_tokens == 1600  # both calls counted


def test_repair_prompt_is_rebuilt_from_the_base_not_compounded(book, entry) -> None:
    providers = editor_providers(ok("FIRST-GARBAGE"), ok("SECOND-GARBAGE"), ok(DELTA))
    result = run_editorial_pass(book, entry, BODY, providers)

    second_repair = providers["mistral"].calls[2].prompt
    assert result.status == "validated"
    assert result.repair_rounds == 2
    assert second_repair.count("Your previous answer was rejected") == 1
    assert "SECOND-GARBAGE" in second_repair
    assert "FIRST-GARBAGE" not in second_repair  # the first rejection is gone


def test_invalid_after_every_repair_fails_closed(book, entry) -> None:
    providers = editor_providers(ok("{}"), ok("{}"), ok("{}"), ok("{}"))
    before = canon_digest(book)
    result = run_editorial_pass(book, entry, BODY, providers)

    assert result.status == "editorial-pending"
    assert result.delta is None
    assert "nothing" in result.reason and "editorial-pending" in result.reason
    assert "chapter_summary" in result.reason  # the last error is quoted
    # max_repair_attempts=2 in the fixture: one original call plus two repairs.
    assert len(providers["mistral"].calls) == 3
    assert canon_digest(book) == before


def test_a_delta_about_the_wrong_chapter_is_not_accepted(book, entry) -> None:
    # Internally consistent, but about a chapter this pass is not reviewing.
    wrong = {
        **DELTA,
        "chapter_number": 4,
        "new_locked_facts": [{**DELTA["new_locked_facts"][0], "source_chapter": 4}],
        "thread_updates": {
            **DELTA["thread_updates"],
            "resolved": [{"thread_id": "T-002", "resolved_in_chapter": 4}],
        },
    }
    result = run_editorial_pass(book, entry, BODY, editor_providers(ok(wrong)))

    assert result.status == "editorial-pending"
    assert result.delta is None
    assert "about chapter 4" in result.reason


def test_no_route_answering_leaves_canon_untouched(book, entry) -> None:
    before = canon_digest(book)
    result = run_editorial_pass(
        book,
        entry,
        BODY,
        editor_providers(TransientFailure("mistral down"), fallback=RateLimited("429")),
    )

    assert result.status == "editorial-pending"
    assert result.delta is None
    assert "No editor route answered" in result.reason
    assert canon_digest(book) == before


def test_fallback_to_the_second_editor_route_is_recorded(book, entry) -> None:
    result = run_editorial_pass(
        book,
        entry,
        BODY,
        editor_providers(
            TransientFailure("mistral down"),
            fallback=ok(DELTA, model="gemini-3.5-flash-lite"),
        ),
    )

    assert result.status == "validated"
    assert result.fallback_triggered is True
    assert result.actual_model == "gemini:gemini-3.5-flash-lite"


def test_a_permanent_failure_never_reaches_the_second_provider(book, entry) -> None:
    """Invariant 3: an auth error is not a reason to spend another quota."""
    providers = editor_providers(
        PermanentFailure("401 invalid key"), fallback=ok(DELTA)
    )
    result = run_editorial_pass(book, entry, BODY, providers)

    assert result.status == "editorial-pending"
    assert providers["gemini"].calls == []


def test_the_pass_writes_nothing_even_when_it_succeeds(book, entry) -> None:
    before = canon_digest(book)
    result = run_editorial_pass(book, entry, BODY, editor_providers(ok(DELTA)))

    assert result.status == "validated"
    assert canon_digest(book) == before
