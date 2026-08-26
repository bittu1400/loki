"""Drafting loop tests against fakes: continuation rounds, fallback,
ADR-0005 failed-stub terminal case, overwrite refusal. No network."""

import re
import shutil
from pathlib import Path

import pytest

from fakes import FakeProvider, full_providers, reset_fixture_state, text_of
from novel_engine.core.config import load_book_config
from novel_engine.core.errors import VaultError
from novel_engine.core.outline import parse_manifest
from novel_engine.core.vault import generated_hash, split_chapter_file
from novel_engine.drafting.generate import (
    STUB_MARKER,
    draft_chapter,
    word_count,
)
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
        "COHERE_API_KEY",
        "GLM_API_KEY",
    )
}


@pytest.fixture
def book(tmp_path: Path):
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    reset_fixture_state(copied)
    config = load_book_config(copied.parent, "example-book", env=FAKE_ENV)
    # Small word target so fakes stay tiny; one continuation round only.
    pipeline = config.pipeline.model_copy(
        update={
            "target_words": 50,
            "word_tolerance": 0.2,  # accept >= 40 words
            "max_continuation_rounds": 1,
            "retry": config.pipeline.retry.model_copy(
                update={
                    "max_attempts": 1,
                    "base_delay_seconds": 0,
                    "jitter": False,
                }
            ),
        }
    )
    object.__setattr__(config, "pipeline", pipeline)
    return config


@pytest.fixture
def entry(book):
    return next(e for e in book.manifest if e.chapter_number == 3)


PROMPT = "# This Chapter\n\nPOV: ovist-rhoam\nBeat: test beat."


# --- happy path -------------------------------------------------------------


def test_success_writes_chapter_and_flips_manifest(book, entry) -> None:
    providers = full_providers(
        openrouter=FakeProvider(Success(text_of(45), "m3", 100, 60, 5))
    )
    result = draft_chapter(book, entry, PROMPT, providers)

    assert result.status == "draft"
    assert result.path is not None and result.path.exists()
    fields, body = split_chapter_file(result.path.read_text())
    assert fields["assigned_model"] == "openrouter:minimax/minimax-m3:free"
    assert fields["actual_model"] == "openrouter:minimax/minimax-m3:free"
    assert fields["fallback_triggered"] is False
    assert fields["continuation_rounds"] == 0
    assert fields["status"] == "draft"
    assert re.fullmatch(r"sess-\d{8}-\d{4}-[0-9a-f]{4}", fields["session_id"])
    # generated_hash matches the stored body (vault primitive owns it).

    assert fields["generated_hash"] == generated_hash(body)

    manifest = parse_manifest((book.root / "canon/plot-outline.md").read_text())
    assert next(e for e in manifest if e.chapter_number == 3).status == "written"


def test_short_draft_triggers_continuation_with_partial_appended(book, entry) -> None:
    provider = FakeProvider(
        Success(text_of(20), "m3", 100, 30, 5),
        Success(text_of(30, seed="x"), "m3", 150, 40, 5),
    )
    result = draft_chapter(book, entry, PROMPT, full_providers(openrouter=provider))

    assert result.continuation_rounds == 1
    assert len(provider.calls) == 2
    second_prompt = provider.calls[1].prompt
    assert PROMPT in second_prompt  # full context re-sent (stateless workers)
    assert "Partial Draft" in second_prompt
    assert text_of(20) in second_prompt  # partial draft appended verbatim
    fields, _ = split_chapter_file(result.path.read_text())  # type: ignore
    assert fields["actual_words"] == word_count(text_of(20) + "\n" + text_of(30, "x"))
    assert fields["input_tokens"] == 250 and fields["output_tokens"] == 70


def test_continuation_hard_capped_and_short_draft_still_accepted(book, entry) -> None:
    # Every response undershoots; after max_continuation_rounds=1 the loop
    # must stop and accept the short draft rather than spin.
    provider = FakeProvider()
    provider.serve(default=Success(text_of(10), "m3", 10, 10, 1))
    result = draft_chapter(book, entry, PROMPT, full_providers(openrouter=provider))
    assert result.continuation_rounds == 1
    assert len(provider.calls) == 2  # initial + one capped round
    assert result.actual_words == word_count(text_of(10) + "\n" + text_of(10))


# --- fallback ----------------------------------------------------------------


def test_rate_limited_primary_falls_back_to_second_route(book, entry) -> None:
    providers = full_providers(
        openrouter=FakeProvider(RateLimited("quota", status_code=429)),
        nvidia=FakeProvider(Success(text_of(45), "m3-nim", 120, 70, 8)),
    )
    result = draft_chapter(book, entry, PROMPT, providers)

    assert result.fallback_triggered is True
    assert result.actual_model == "nvidia:minimaxai/minimax-m3"
    fields, _ = split_chapter_file(result.path.read_text())  # type: ignore
    assert fields["fallback_triggered"] is True
    assert fields["assigned_model"] != fields["actual_model"]


def test_permanent_failure_never_walks_the_chain(book, entry) -> None:

    fallback_provider = FakeProvider()
    providers = full_providers(
        openrouter=FakeProvider(PermanentFailure("auth error", status_code=401)),
        nvidia=fallback_provider,
    )
    result = draft_chapter(book, entry, PROMPT, providers)

    assert fallback_provider.calls == []  # never contacted
    assert result.status == "failed-stub"


# --- ADR-0005 failed stub ----------------------------------------------------


def test_all_routes_exhausted_writes_stub_manifest_untouched(book, entry) -> None:

    providers = {
        "openrouter": FakeProvider(RateLimited("quota")),
        "nvidia": FakeProvider(TransientFailure("timeout")),
        "groq": FakeProvider(RateLimited("429 again")),
    }
    result = draft_chapter(book, entry, PROMPT, providers)

    assert result.status == "failed-stub"
    assert result.path is not None and result.path.exists()
    body = result.path.read_text()
    assert STUB_MARKER in body
    assert "groq:openai/gpt-oss-120b" in body  # last error recorded
    fields, _ = split_chapter_file(body)
    assert fields["status"] == "failed-stub"
    assert fields["actual_words"] == 0

    manifest = parse_manifest((book.root / "canon/plot-outline.md").read_text())
    assert next(e for e in manifest if e.chapter_number == 3).status == "planned"


def test_stub_replaced_by_rerun_with_overwrite(book, entry) -> None:

    dead = {
        "openrouter": FakeProvider(TransientFailure("down")),
        "nvidia": FakeProvider(TransientFailure("down")),
        "groq": FakeProvider(TransientFailure("down")),
    }
    first = draft_chapter(book, entry, PROMPT, dead)
    with pytest.raises(VaultError, match="Refusing to overwrite"):
        draft_chapter(book, entry, PROMPT, dead)

    healthy = full_providers(
        openrouter=FakeProvider(Success(text_of(45), "m3", 100, 60, 5))
    )
    second = draft_chapter(book, entry, PROMPT, healthy, allow_overwrite=True)
    assert second.status == "draft"
    assert STUB_MARKER not in second.path.read_text()  # type: ignore[union-attr]
    # The manifest flip happens on this successful pass (was still planned).
    manifest = parse_manifest((book.root / "canon/plot-outline.md").read_text())
    assert next(e for e in manifest if e.chapter_number == 3).status == "written"
    del first
