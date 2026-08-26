"""CLI wiring tests: dry-run spends nothing, refusal paths, full run with
fakes, audit JSON, failed-stub exit code."""

import io
import json
import shutil
from pathlib import Path

import pytest
from rich.console import Console

from fakes import FakeProvider, full_providers, text_of
from novel_engine.cli.write_session import run_session
from novel_engine.core.outline import parse_manifest
from novel_engine.providers.base import RateLimited, Success

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
def vault(tmp_path: Path) -> Path:
    copied = tmp_path / "vault"
    copied.mkdir()
    shutil.copytree(FIXTURE, copied / "example-book")
    return copied


def null_console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False)


@pytest.fixture
def book(vault):
    # Shrink the word target so fake drafts satisfy it, and kill retry
    # backoff so an all-routes-fail test doesn't sleep through real
    # exponential delays.
    pipeline_path = vault / "example-book/config/pipeline.yaml"
    text = pipeline_path.read_text()
    text = text.replace("target_words: 1000", "target_words: 50")
    text = text.replace("max_attempts: 4", "max_attempts: 1")
    text = text.replace("base_delay_seconds: 1", "base_delay_seconds: 0")
    text = text.replace("jitter: true", "jitter: false")
    pipeline_path.write_text(text)
    return vault


# --- dry run -----------------------------------------------------------------


def test_dry_run_prints_prompt_and_spends_nothing(book, capsys) -> None:
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        dry_run=True,
        console=null_console(),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Ovist pulls nine years of countersignature gaps" in out
    assert "{{beat}}" not in out  # slots actually filled
    assert "Write this chapter in full" in out


def test_dry_run_does_not_touch_chapters_or_sessions(book, capsys) -> None:
    run_session("example-book", book, FAKE_ENV, dry_run=True, console=null_console())
    chapters = list((book / "example-book/chapters").glob("chapter-*.md"))
    assert [p.name for p in chapters] == ["chapter-001.md", "chapter-002.md"]
    assert new_session_files(book) == []


# --- refusals ----------------------------------------------------------------


def test_unknown_book_fails_with_actionable_error(book, capsys) -> None:
    with pytest.raises(Exception, match="new-book --slug ghost"):
        run_session("ghost-book", book, FAKE_ENV, console=null_console())


def test_existing_chapter_refused_without_force(book, capsys) -> None:
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        chapter=1,
        providers=full_providers(),
        console=null_console(),
    )
    assert code == 1


def test_force_without_tty_refuses_confirmation(book, capsys) -> None:
    # Non-interactive stdin: confirmation cannot be given; fail closed.
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        chapter=1,
        force=True,
        providers=full_providers(),
        console=null_console(),
    )
    assert code == 1


# --- full run with fakes ------------------------------------------------------


def test_full_run_writes_chapter_audit_and_flips_manifest(book) -> None:
    providers = full_providers(
        openrouter=FakeProvider(Success(text_of(45), "m3", 100, 60, 5))
    )
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=providers,
        console=null_console(),
    )
    assert code == 0

    chapter3 = book / "example-book/chapters/chapter-003.md"
    assert chapter3.exists()
    manifest = parse_manifest((book / "example-book/canon/plot-outline.md").read_text())
    assert next(e for e in manifest if e.chapter_number == 3).status == "written"

    sessions = new_session_files(book)
    assert len(sessions) == 1
    payload = json.loads(sessions[0].read_text())
    assert payload["chapter_number"] == 3
    assert payload["final_phase"] == "draft"
    assert payload["calls"][0]["provider"] == "openrouter"


PREEXISTING_SESSIONS = ("sess-20260820-1930-c41a.json", "sess-20260822-0915-b7e2.json")


def new_session_files(vault_root: Path) -> list[Path]:
    """Session JSONs created by the run — the fixture ships two already."""
    directory = vault_root / "example-book/log/sessions"
    return sorted(
        p for p in directory.glob("sess-*.json") if p.name not in PREEXISTING_SESSIONS
    )


def test_all_routes_fail_stub_exit_code_one(book) -> None:
    dead = {
        name: FakeProvider(RateLimited("down"))
        for name in ("openrouter", "nvidia", "groq")
    }
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=dead,
        console=null_console(),
    )
    assert code == 1
    stub = book / "example-book/chapters/chapter-003.md"
    assert stub.exists()
    manifest = parse_manifest((book / "example-book/canon/plot-outline.md").read_text())
    assert next(e for e in manifest if e.chapter_number == 3).status == "planned"

    assert len(new_session_files(book)) == 1
