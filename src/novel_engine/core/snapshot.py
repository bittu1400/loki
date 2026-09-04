"""Per-session vault snapshots — the recovery path ADR-0004 removed (OQ-01).

ADR-0004 gitignores real manuscripts, which was right for privacy and
left a hole: several safeguards in this design assume git history can
recover a corrupted tracker, and for a real book that history does not
exist. A bad delta, an errant `--force`, or a disk failure had no undo.

So each real book becomes its own git repository at `vault/<slug>/.git`,
nested inside the outer repo and invisible to it (everything under
`vault/` except the fixture is gitignored). The engine commits twice per
session — the author's edits before it starts, its own writes after it
ends — so "undo that session" is `git -C vault/<slug> checkout HEAD~1`
and "what did it change" is `git -C vault/<slug> show`.

**This module never mutates a working-tree file.** It runs `git add` and
`git commit`, which write only `.git`. Restoring is deliberately NOT
implemented: an engine that can check out old content is an engine that
can overwrite author prose without `--force` (invariant 5), and plain
git already does it better than a wrapper would.

**No remote is ever configured and nothing is ever pushed.** The privacy
property ADR-0004 bought is not for sale; this only adds local history.

Books already tracked by an enclosing repository are skipped, not
double-versioned: `vault/example-book/` is committed to THIS repo, which
is already its history.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Used only when the machine has no git identity configured. A real
#: author's name and email are preferred and left alone when present.
FALLBACK_NAME = "novel-engine"
FALLBACK_EMAIL = "novel-engine@localhost"


@dataclass(frozen=True)
class SnapshotState:
    """Whether this book has session history, and why not when it does not."""

    #: The book keeps its own repo and commits land in it.
    active: bool
    #: Set when snapshots are off. Human-readable, actionable.
    reason: str = ""
    #: True when an enclosing repo already versions this book (the
    #: fixture). Not a failure: it has history, just not its own.
    externally_tracked: bool = False


def _run(book_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(book_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _identity_args(book_root: Path) -> list[str]:
    """Borrow the machine's git identity; supply one only if it has none.

    A commit with no configured identity fails outright, and a session
    that cannot snapshot is a session with no undo.
    """
    configured = _run(book_root, ["config", "user.email"])
    if configured.returncode == 0 and configured.stdout.strip():
        return []
    return [
        "-c",
        f"user.name={FALLBACK_NAME}",
        "-c",
        f"user.email={FALLBACK_EMAIL}",
    ]


def has_own_repo(book_root: Path) -> bool:
    return (book_root / ".git").exists()


def externally_tracked(book_root: Path) -> bool:
    """True when a repo above this book already tracks its files.

    `vault/example-book/` is committed to the outer repository, so it
    already has exactly the history OQ-01 asks for. Initialising a nested
    repo inside it would create two histories of the same bytes.
    """
    listed = _run(book_root, ["ls-files"])
    return listed.returncode == 0 and bool(listed.stdout.strip())


def ensure_repo(book_root: Path) -> SnapshotState:
    """Make sure this book has a restorable history, creating one if not.

    Returns state rather than raising: the caller decides whether a book
    without history may proceed, and that answer depends on whether the
    session is going to write canon.
    """
    try:
        if has_own_repo(book_root):
            return SnapshotState(active=True)
        if externally_tracked(book_root):
            return SnapshotState(
                active=False,
                externally_tracked=True,
                reason=(
                    f"{book_root} is already tracked by an enclosing git "
                    "repository, which is its history. No nested repo created."
                ),
            )
        created = _run(book_root, ["init", "--quiet"])
        if created.returncode != 0:
            return SnapshotState(
                active=False,
                reason=f"git init failed in {book_root}: {created.stderr.strip()}",
            )
        return SnapshotState(active=True)
    except FileNotFoundError:
        return SnapshotState(
            active=False,
            reason=(
                "git is not installed or not on PATH, so this book has no "
                "recovery path (OQ-01). Install git, or run with "
                "editorial.enabled: false to draft without writing canon."
            ),
        )
    except OSError as exc:  # pragma: no cover - environment-specific
        return SnapshotState(active=False, reason=f"Cannot run git: {exc}")


def snapshot(book_root: Path, message: str) -> str | None:
    """Commit everything in the book. Returns the short sha, or None.

    None means there was nothing to commit — the common case for the
    pre-session snapshot when the author has not touched anything.
    """
    if not has_own_repo(book_root):
        return None
    if _run(book_root, ["add", "-A"]).returncode != 0:
        return None
    committed = _run(
        book_root, [*_identity_args(book_root), "commit", "-m", message, "--quiet"]
    )
    if committed.returncode != 0:
        # "nothing to commit" is the expected no-op, not a failure.
        return None
    return _run(book_root, ["rev-parse", "--short", "HEAD"]).stdout.strip() or None
