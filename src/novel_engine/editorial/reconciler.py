"""Deterministic append-only application of a validated delta.

The only component that changes canon. It accepts an EditorialDelta —
never a string, never a dict, never model output — and turns its
validated fields into lines through the vault primitives. Every line
written here is built in Python from typed fields; no model text is ever
copied into a canon body (invariant 1, pitfall A1).

All or nothing (invariant 2, pitfall A2). The whole apply runs inside
`vault.canon_transaction`, so a failure at the fourth append restores
the three that already landed. A delta is applied completely or not at
all; there is no partial success and no "we saved what we could".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from novel_engine.core.config import BookConfig
from novel_engine.core.vault import (
    append_deepen_question,
    append_fact,
    append_summary,
    append_thread,
    canon_transaction,
    flip_thread_status,
)
from novel_engine.editorial.schema import EditorialDelta

#: Every file the reconciler may touch. Snapshotted as one unit.
CANON_FILES = (
    "canon/continuity-tracker.md",
    "canon/open-threads.md",
    "canon/deepen-queue.md",
    "log/chapter-summary.md",
)


@dataclass
class Reconciliation:
    """What was actually appended. Reported, audited, never re-derived."""

    chapter_number: int
    facts_added: list[str] = field(default_factory=list)
    threads_opened: list[str] = field(default_factory=list)
    threads_resolved: list[str] = field(default_factory=list)
    questions_added: list[str] = field(default_factory=list)
    summary_added: bool = False
    patches_path: Path | None = None

    @property
    def canon_lines_added(self) -> int:
        return (
            len(self.facts_added)
            + len(self.threads_opened)
            + len(self.questions_added)
            + int(self.summary_added)
        )


def patches_markdown(delta: EditorialDelta, session_id: str) -> str:
    """The suggested-patches report (specs §12).

    Suggestions about author-owned files: written to a session log so the
    author finds them later, never applied, and never printed only to
    stdout where an automated run would lose them. `target_file` is
    quoted as text — it is not, and must never become, a write path.
    """
    lines = [
        f"# Suggested canon patches — {session_id}",
        "",
        f"Chapter {delta.chapter_number:03d}.",
        "",
        "Suggestions only. The engine never applies these; the files they "
        "name are author-owned (architecture.md §3).",
        "",
    ]
    for patch in delta.suggested_canon_patches:
        lines += [
            f"## `{patch.target_file}`",
            "",
            f"**Why:** {patch.rationale}",
            "",
            f"**Suggested:** {patch.suggested_text}",
            "",
        ]
    return "\n".join(lines)


def reconcile(
    book: BookConfig,
    delta: EditorialDelta,
    *,
    session_id: str,
) -> Reconciliation:
    """Apply a validated delta to canon. All of it, or none of it.

    Raises VaultError if any step is refused — with canon restored to
    its pre-application bytes and the snapshot location named. Callers
    treat that as `editorial-pending`: nothing was appended.
    """
    root = book.root
    result = Reconciliation(chapter_number=delta.chapter_number)

    with canon_transaction([root / relative for relative in CANON_FILES]):
        # Summary first: it is the append most likely to be refused
        # (one paragraph per chapter, in chapter order), so a re-run of
        # an already-reconciled chapter stops before touching the
        # ledgers rather than after.
        append_summary(root, delta.chapter_number, delta.chapter_summary)
        result.summary_added = True

        for fact in delta.new_locked_facts:
            result.facts_added.append(
                append_fact(
                    root,
                    fact.category,
                    fact.entity,
                    fact.source_chapter,
                    fact.fact,
                )
            )

        for opened in delta.thread_updates.opened:
            result.threads_opened.append(
                append_thread(root, delta.chapter_number, opened.text)
            )

        # `progressed` updates change no file: specs §5 forbids
        # rewriting thread text, and a note is not a status. It reaches
        # the author through the session audit's copy of the delta.
        for resolved in delta.thread_updates.resolved:
            flip_thread_status(root, resolved.thread_id, resolved.resolved_in_chapter)
            result.threads_resolved.append(resolved.thread_id)

        for question in delta.deepen_questions:
            result.questions_added.append(
                append_deepen_question(root, delta.chapter_number, question)
            )

    # Outside the transaction: a session log, not canon. Written after
    # the canon change succeeded so a rolled-back apply leaves no report
    # of changes that did not happen.
    if delta.suggested_canon_patches:
        path = root / "log" / "sessions" / f"{session_id}-patches.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(patches_markdown(delta, session_id), encoding="utf-8")
        result.patches_path = path

    return result
