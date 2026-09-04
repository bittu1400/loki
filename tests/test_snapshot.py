"""Per-session vault snapshots (OQ-01, decision #40, ADR-0013).

The property under test is the one OQ-01 asked for and nothing more:
after a session there exists a commit to go back to, and the author's own
edits are a separate commit from the engine's writes — so undoing a
session does not also undo the author's morning.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from fakes import reset_fixture_state
from novel_engine.core.snapshot import (
    ensure_repo,
    externally_tracked,
    has_own_repo,
    snapshot,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    reset_fixture_state(copied)
    return copied


def log_lines(book_root: Path) -> list[str]:
    done = subprocess.run(
        ["git", "-C", str(book_root), "log", "--format=%s"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in done.stdout.splitlines() if line]


def test_ensure_repo_creates_history_for_an_unversioned_book(book_root: Path) -> None:
    assert not has_own_repo(book_root)
    state = ensure_repo(book_root)
    assert state.active
    assert has_own_repo(book_root)


def test_ensure_repo_is_idempotent(book_root: Path) -> None:
    ensure_repo(book_root)
    assert ensure_repo(book_root).active


def test_committed_fixture_is_left_alone(tmp_path: Path) -> None:
    """vault/example-book/ is versioned by THIS repo already. A nested
    repo inside it would be a second history of the same bytes."""
    assert externally_tracked(FIXTURE)
    state = ensure_repo(FIXTURE)
    assert not state.active
    assert state.externally_tracked
    assert not (FIXTURE / ".git").exists()


def test_snapshot_commits_and_reports_a_sha(book_root: Path) -> None:
    ensure_repo(book_root)
    sha = snapshot(book_root, "baseline")
    assert sha
    assert log_lines(book_root) == ["baseline"]


def test_snapshot_of_an_unchanged_book_is_a_no_op(book_root: Path) -> None:
    ensure_repo(book_root)
    snapshot(book_root, "baseline")
    assert snapshot(book_root, "nothing changed") is None
    assert log_lines(book_root) == ["baseline"]


def test_snapshot_captures_a_later_change(book_root: Path) -> None:
    ensure_repo(book_root)
    snapshot(book_root, "baseline")
    (book_root / "canon" / "continuity-tracker.md").write_text(
        "rewritten by hand", encoding="utf-8"
    )

    assert snapshot(book_root, "author edits") is not None
    assert log_lines(book_root) == ["author edits", "baseline"]

    # The point of the whole exercise: the previous bytes are recoverable.
    restored = subprocess.run(
        ["git", "-C", str(book_root), "show", "HEAD~1:canon/continuity-tracker.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Continuity Tracker" in restored.stdout


def test_snapshot_without_a_repo_does_nothing(book_root: Path) -> None:
    assert snapshot(book_root, "no repo here") is None


def test_missing_git_is_reported_not_raised(book_root: Path, monkeypatch) -> None:
    """A machine without git must produce an actionable refusal upstream,
    never a traceback and never a silent success."""

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    state = ensure_repo(book_root)
    assert not state.active
    assert "git is not installed" in state.reason
    assert "editorial.enabled: false" in state.reason


def test_no_remote_is_ever_configured(book_root: Path) -> None:
    """ADR-0004's privacy property is not for sale: local history only."""
    ensure_repo(book_root)
    snapshot(book_root, "baseline")
    remotes = subprocess.run(
        ["git", "-C", str(book_root), "remote"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert remotes.stdout.strip() == ""
