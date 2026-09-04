"""CLI wiring tests: dry-run spends nothing, refusal paths, full run with
fakes, audit JSON, failed-stub exit code."""

import io
import json
import shutil
from pathlib import Path

import pytest
from rich.console import Console

from fakes import (
    FakeProvider,
    editorial_delta,
    full_providers,
    reset_fixture_state,
    text_of,
)
from novel_engine.cli.write_session import run_session
from novel_engine.core.outline import parse_manifest
from novel_engine.core.state_machine import NextStep
from novel_engine.core.vault import (
    read_next_step,
    split_chapter_file,
    write_next_step,
)
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
    reset_fixture_state(copied / "example-book")
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
    providers = drafting_and_editorial()
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
    assert payload["final_phase"] == "complete"  # the phase the run reached
    assert payload["calls"][0]["provider"] == "openrouter"


def new_session_files(vault_root: Path) -> list[Path]:
    """Session JSONs created by the run — reset_fixture_state cleared
    everything the committed fixture shipped with."""
    return sorted((vault_root / "example-book/log/sessions").glob("sess-*.json"))


def test_all_routes_fail_stub_exit_code_one(book) -> None:
    dead = {
        name: FakeProvider(RateLimited("down"))
        for name in ("openrouter", "nvidia", "groq", "local")
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


def test_dry_run_env_var(monkeypatch, book, capsys) -> None:
    from novel_engine.cli.write_session import main

    monkeypatch.setenv("DRY_RUN", "1")
    code = main(["--book", "example-book", "--vault-root", str(book.resolve())])
    assert code == 0
    assert new_session_files(book) == []
    assert not (book / "example-book/chapters/chapter-003.md").exists()
    assert "Ovist pulls nine years" in capsys.readouterr().out


# --- Phase 6: state machine, resume, and the review phases --------------------


def drafting_and_editorial(
    delta: dict | None = None, editor: FakeProvider | None = None
) -> dict[str, FakeProvider]:
    """A provider set that can carry a session all the way to `complete`:
    openrouter drafts ch-003 (ovist-rhoam's route), gemini edits it."""
    return full_providers(
        openrouter=FakeProvider(Success(text_of(45), "m3", 60, 5, 100)),
        gemini=editor
        or FakeProvider(
            Success(json.dumps(delta or editorial_delta(3)), "flash-lite", 800, 300, 90)
        ),
    )


def plan_chapter_four(vault_root: Path) -> None:
    """reset_fixture_state trims the manifest to rows 1-3; give the book
    somewhere for the pointer to advance TO."""
    path = vault_root / "example-book/canon/plot-outline.md"
    text = path.read_text(encoding="utf-8")
    row = "| 004 | brannec-tull | arc-1 | planned | Sela Vosk names her price. |\n"
    path.write_text(
        text.replace("<!-- MANIFEST:END -->", row + "<!-- MANIFEST:END -->")
    )


def pointer(vault_root: Path):
    return read_next_step(vault_root / "example-book")


def park_at(vault_root: Path, phase: str, *, chapter: int = 3, **fields) -> None:
    """Put log/next-step.md into a mid-flight phase, as a crash would."""
    write_next_step(
        vault_root / "example-book",
        NextStep(
            next_chapter=chapter,
            next_pov="ovist-rhoam",
            last_session_id="sess-20260904-1200-aaaa",
            last_session_phase=phase,
            last_session_status=phase,
            **fields,
        ),
    )


def canon_bytes(vault_root: Path) -> dict[str, str]:
    root = vault_root / "example-book"
    return {
        name: (root / name).read_text(encoding="utf-8")
        for name in (
            "canon/continuity-tracker.md",
            "canon/open-threads.md",
            "canon/deepen-queue.md",
            "log/chapter-summary.md",
        )
    }


def audit_payload(vault_root: Path) -> dict:
    files = new_session_files(vault_root)
    assert len(files) == 1, files
    return json.loads(files[0].read_text())


def test_completed_session_promotes_chapter_and_advances_pointer(book) -> None:
    plan_chapter_four(book)
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=null_console(),
    )
    assert code == 0

    fields, _ = split_chapter_file(
        (book / "example-book/chapters/chapter-003.md").read_text(encoding="utf-8")
    )
    assert fields["status"] == "pending-review"

    step = pointer(book)
    assert step.last_session_phase == "complete"
    assert step.next_chapter == 4  # the next planned manifest row, not 3
    assert step.next_pov == "brannec-tull"
    # specs §12: the delta's next_step_note is the pointer's prose half.
    assert step.note == "Sela has not been told."

    # specs §13: the deterministic metrics belong in the session record.
    payload = audit_payload(book)
    assert payload["style_metrics"]["word_count"] == 45
    assert payload["resumed"] is False


def test_completed_session_appends_canon_and_writes_an_editorial_audit(book) -> None:
    before = canon_bytes(book)
    run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=null_console(),
    )
    after = canon_bytes(book)

    assert "Ovist counts driftglass by weight." in after["canon/continuity-tracker.md"]
    assert "Someone reset the ebb ledge." in after["canon/open-threads.md"]
    assert "Ovist walked the ledge" in after["log/chapter-summary.md"]
    for name, text in before.items():
        # Append-only: canon grows, and not one existing line is rewritten.
        assert len(after[name]) > len(text)
        for line in text.splitlines():
            assert line in after[name]

    payload = audit_payload(book)["editorial"]
    assert payload["status"] == "validated"
    assert payload["applied"]["summary_added"] is True
    # specs §12: the delta is the only place a `progressed` note reaches
    # the author, so the audit must carry it whole.
    assert payload["delta"]["chapter_summary"].startswith("Ovist walked")


def test_interrupted_session_refuses_and_names_the_phase(book, capsys) -> None:
    park_at(book, "drafted")
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    text = console_out.getvalue()
    assert "chapter 003" in text
    assert "'drafted'" in text
    assert "--resume" in text


def test_resume_with_nothing_to_resume_refuses(book) -> None:
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        resume=True,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    assert "nothing to resume" in console_out.getvalue()


def test_chapter_override_refused_while_another_session_is_open(book) -> None:
    park_at(book, "styled", chapter=3)
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        chapter=1,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    assert "records chapter 003" in console_out.getvalue()


def test_blocked_pointer_refuses_before_anything_runs(book) -> None:
    park_at(book, "complete", blocked=True, blocked_reason="quota exhausted")
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    assert "quota exhausted" in console_out.getvalue()
    assert not (book / "example-book/chapters/chapter-003.md").exists()


def test_resume_runs_the_review_phases_without_redrafting(book) -> None:
    # First run: draft only, with a dead editor, so the session parks.
    dead_editor = full_providers(
        openrouter=FakeProvider(Success(text_of(45), "m3", 60, 5, 100)),
    )
    assert (
        run_session(
            "example-book",
            book,
            FAKE_ENV,
            providers=dead_editor,
            console=null_console(),
        )
        == 2
    )
    assert pointer(book).last_session_phase == "editorial-pending"
    drafted = (book / "example-book/chapters/chapter-003.md").read_text()

    # Second run resumes: the editor answers, and the prose is untouched.
    providers = drafting_and_editorial()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        resume=True,
        providers=providers,
        console=null_console(),
    )
    assert code == 0
    assert pointer(book).last_session_phase == "complete"
    assert providers["openrouter"].calls == []  # no second draft
    body = (book / "example-book/chapters/chapter-003.md").read_text()
    assert split_chapter_file(body)[1] == split_chapter_file(drafted)[1]


def test_editorial_pending_exits_two_and_leaves_canon_untouched(book) -> None:
    before = canon_bytes(book)
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=full_providers(
            openrouter=FakeProvider(Success(text_of(45), "m3", 60, 5, 100)),
            gemini=FakeProvider(RateLimited("editor down")),
            mistral=FakeProvider(RateLimited("editor down")),
        ),
        console=null_console(),
    )
    assert code == 2
    assert canon_bytes(book) == before
    assert pointer(book).last_session_phase == "editorial-pending"

    fields, _ = split_chapter_file(
        (book / "example-book/chapters/chapter-003.md").read_text(encoding="utf-8")
    )
    assert fields["status"] == "draft"  # drafted, not finished


def test_critical_violation_refuses_the_whole_delta(book) -> None:
    """Invariant 6 / decision #29, reached through the CLI this time."""
    contradiction = editorial_delta(
        3,
        continuity_violations=[
            {
                "severity": "critical",
                "violated_fact": "The spring-tide page carries two corrections.",
                "chapter_excerpt": "nine corrections on the spring-tide page",
                "explanation": "Contradicts a locked fact from ch-001.",
            }
        ],
    )
    before = canon_bytes(book)
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(contradiction),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 2
    assert canon_bytes(book) == before
    assert pointer(book).last_session_phase == "editorial-pending"
    assert "contradicts locked canon" in console_out.getvalue()


def test_editorial_disabled_completes_without_touching_canon(book) -> None:
    pipeline_path = book / "example-book/config/pipeline.yaml"
    pipeline_path.write_text(
        pipeline_path.read_text().replace("enabled: true", "enabled: false")
    )
    before = canon_bytes(book)
    providers = drafting_and_editorial()

    code = run_session(
        "example-book", book, FAKE_ENV, providers=providers, console=null_console()
    )

    assert code == 0
    assert canon_bytes(book) == before
    assert providers["gemini"].calls == []  # the editor was never asked
    assert pointer(book).last_session_phase == "complete"
    assert "editorial" not in audit_payload(book)


def test_dry_run_on_a_drafted_chapter_assembles_nothing(book) -> None:
    run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=full_providers(
            openrouter=FakeProvider(Success(text_of(45), "m3", 60, 5, 100)),
        ),
        console=null_console(),
    )
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        resume=True,
        dry_run=True,
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 0
    assert "nothing to assemble" in console_out.getvalue()


def test_pointer_disagreeing_with_disk_refuses(book) -> None:
    park_at(book, "drafted")  # says drafted; chapter-003.md does not exist
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        resume=True,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    assert "pointer disagrees with disk" in console_out.getvalue()


# --- OQ-01: every session leaves a commit to go back to ----------------------


def git_log(vault_root: Path) -> list[str]:
    import subprocess

    done = subprocess.run(
        ["git", "-C", str(vault_root / "example-book"), "log", "--format=%s"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in done.stdout.splitlines() if line]


def test_session_leaves_a_baseline_and_a_session_commit(book) -> None:
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=null_console(),
    )
    assert code == 0

    log = git_log(book)
    assert len(log) == 2
    assert log[0].endswith("chapter 3 complete")
    assert log[1].startswith("author edits before session")


def test_author_edits_are_committed_separately_from_engine_writes(book) -> None:
    """Undoing a session must not also undo the author's morning."""
    import subprocess

    tracker = book / "example-book/canon/continuity-tracker.md"
    tracker.write_text(
        tracker.read_text() + "\nAn author note added by hand.\n", encoding="utf-8"
    )

    run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=null_console(),
    )

    # One commit back is the state the session started from: the author's
    # note present, the session's canon line absent.
    before = subprocess.run(
        [
            "git",
            "-C",
            str(book / "example-book"),
            "show",
            "HEAD~1:canon/continuity-tracker.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "An author note added by hand." in before
    assert "Ovist counts driftglass by weight." not in before
    assert "Ovist counts driftglass by weight." in tracker.read_text()


def test_editorial_pending_session_is_still_snapshotted(book) -> None:
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=full_providers(
            openrouter=FakeProvider(Success(text_of(45), "m3", 60, 5, 100)),
            gemini=FakeProvider(RateLimited("editor down")),
            mistral=FakeProvider(RateLimited("editor down")),
        ),
        console=null_console(),
    )
    assert code == 2
    assert git_log(book)[0].endswith("chapter 3 editorial-pending")


def test_no_git_refuses_a_canon_writing_session(book, monkeypatch) -> None:
    """OQ-01 in one test: no recovery path, no canon."""
    import novel_engine.core.snapshot as snapshot_module

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(snapshot_module.subprocess, "run", no_git)
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    assert "no recovery path" in console_out.getvalue()
    assert not (book / "example-book/chapters/chapter-003.md").exists()


def test_no_git_still_allows_a_drafting_only_session(book, monkeypatch) -> None:
    """editorial.enabled: false writes no canon, so it needs no undo."""
    import novel_engine.core.snapshot as snapshot_module

    pipeline_path = book / "example-book/config/pipeline.yaml"
    pipeline_path.write_text(
        pipeline_path.read_text().replace("enabled: true", "enabled: false")
    )
    monkeypatch.setattr(
        snapshot_module.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git")),
    )
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 0
    assert "no snapshots" in console_out.getvalue()
    assert (book / "example-book/chapters/chapter-003.md").exists()


def test_rerun_after_a_failed_stub_names_force_not_resume(book) -> None:
    """An all-routes-exhausted run leaves the phase at 'target' with a stub
    on disk. Pointing the author at --resume would send them to a flag that
    then refuses for the stub; --force is the answer, so say it first."""
    dead = {
        name: FakeProvider(RateLimited("down"))
        for name in ("openrouter", "nvidia", "groq", "local")
    }
    assert (
        run_session(
            "example-book", book, FAKE_ENV, providers=dead, console=null_console()
        )
        == 1
    )
    assert pointer(book).last_session_phase == "target"

    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        providers=dead,
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    text = console_out.getvalue()
    assert "--force" in text
    assert "interrupted session" not in text


def test_resume_at_target_says_there_is_nothing_to_continue(book) -> None:
    park_at(book, "target")
    console_out = io.StringIO()
    code = run_session(
        "example-book",
        book,
        FAKE_ENV,
        resume=True,
        providers=drafting_and_editorial(),
        console=Console(file=console_out, force_terminal=False, width=200),
    )
    assert code == 1
    assert "never produced a draft" in console_out.getvalue()
