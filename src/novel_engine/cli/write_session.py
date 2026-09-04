"""Single-chapter session entry point (ADR-0003).

Runs the specs §11 lifecycle for one chapter — target, drafted, styled,
[editorial-pending | reconciled], complete — writing every artifact
through core/vault.py and persisting each phase to log/next-step.md
before the next one starts, so any interruption is resumable.

Three outcomes, three exit codes (specs §15): 0 the chapter finished and
is pending-review, 1 nothing ran or every route failed, 2 the prose is on
disk but the review did not reconcile and canon was deliberately left
untouched. The violation list is ADVISORY in all three — number
disagreements are the one class proven caught (OQ-10).

--dry-run prints the exact assembled prompt and exits BEFORE any provider
construction or API call, because prompt tuning is the highest-iteration
activity in the project and free-tier quota is its hardest constraint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console

from novel_engine.core.config import BookConfig, load_book_config
from novel_engine.core.context_builder import AssembledPrompt, build_prompt
from novel_engine.core.errors import (
    ConfigError,
    EditorialError,
    NovelEngineError,
    VaultError,
)
from novel_engine.core.outline import ChapterEntry, parse_manifest, resolve_target
from novel_engine.core.snapshot import ensure_repo, snapshot
from novel_engine.core.state_machine import SessionStateMachine
from novel_engine.core.vault import (
    chapter_path,
    flip_chapter_status,
    split_chapter_file,
)
from novel_engine.drafting.generate import DraftResult, draft_chapter, make_session_id
from novel_engine.editorial.pass_runner import EditorialResult, run_editorial_pass
from novel_engine.editorial.reconciler import Reconciliation, reconcile
from novel_engine.providers.audit import CallRecorder
from novel_engine.providers.base import Provider
from novel_engine.quality.style_checks import build_report

CONFIRM_WORD = "replace"

#: specs §15. A chapter drafted whose review did not reconcile: prose on
#: disk, canon deliberately untouched, session resumable (decision #37).
EXIT_EDITORIAL_PENDING = 2

#: Phases whose chapter is already on disk. Resuming into one of these
#: never re-drafts: the prose exists and the engine does not replace it
#: without --force (invariant 5).
DRAFT_DONE_PHASES = frozenset({"drafted", "styled", "editorial-pending", "reconciled"})


def _end_session(
    config: BookConfig,
    session_id: str,
    audit: dict[str, object],
    final_phase: str,
) -> Path:
    """Write the session record, then snapshot the vault (specs §13, §18).

    The audit is written at session end and not after drafting, because a
    session no longer ends there: the phase it records is the phase the
    run actually reached, which is the same string the pointer carries.

    The snapshot comes last so the commit contains the audit that
    describes it, which makes `git -C vault/<slug> show` a complete
    account of one session (ADR-0013).
    """
    audit["final_phase"] = final_phase
    path = config.root / "log" / "sessions" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")

    chapter = audit.get("chapter_number")
    snapshot(config.root, f"session {session_id}: chapter {chapter} {final_phase}")
    return path


def _draft_audit(assembled: AssembledPrompt, result: DraftResult) -> dict[str, object]:
    """The drafting half of the session record. No secrets, no raw prompt."""
    return {
        "pov": assembled.pov,
        "beat": assembled.beat,
        "assigned_model": result.assigned_model,
        "actual_model": result.actual_model,
        "fallback_triggered": result.fallback_triggered,
        "continuation_rounds": result.continuation_rounds,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "calls": [
            {
                "provider": attempt.provider,
                "model_id": attempt.model_id,
                "outcome": attempt.outcome,
                "latency_ms": attempt.latency_ms,
                "error": attempt.message[:500] or None,
            }
            for attempt in result.attempts
        ],
    }


def _confirm_overwrite(console: Console, path: Path) -> bool:
    if not sys.stdin.isatty():
        # No human at the keyboard to confirm a destructive action;
        # fail closed rather than guess.
        console.print(
            "[red]refusing[/red] --force needs interactive confirmation "
            "(no TTY attached)."
        )
        return False
    console.print(
        f"[yellow]destructive[/yellow] {path} exists and will be "
        f"REPLACED. Type '{CONFIRM_WORD}' to proceed."
    )
    try:
        reply = input(f"type '{CONFIRM_WORD}': ").strip().lower()
    except EOFError:
        reply = ""
    return reply == CONFIRM_WORD


def _resume_refusal(
    console: Console,
    book_slug: str,
    machine: SessionStateMachine,
    entry: ChapterEntry,
) -> int:
    """specs §11: refuse with a message precise enough to act on."""
    console.print(
        f"[red]interrupted session[/red] chapter {entry.chapter_number:03d} "
        f"is at phase '{machine.phase}' in log/next-step.md."
    )
    console.print(
        f"Resume it:   write-session --book {book_slug} --resume\n"
        f"Or restart:  write-session --book {book_slug} --force "
        "(replaces the prose)"
    )
    console.print("Nothing ran; no prose and no canon were touched.")
    return 1


def _style_phase(
    config: BookConfig,
    entry: ChapterEntry,
    machine: SessionStateMachine,
    body: str,
    target_words: object,
    *,
    session_id: str,
    audit: dict[str, object],
    console: Console,
) -> None:
    """Deterministic checks. Costs nothing, judges nothing (specs §14)."""
    guide_path = config.root / "canon" / "style-guide.md"
    report = build_report(
        config.slug,
        entry.chapter_number,
        body,
        guide_path.read_text(encoding="utf-8"),
        target_words=target_words if isinstance(target_words, int) else None,
        style_guide_path=guide_path,
    )
    machine.transition("styled", session_id=session_id, status="styled")
    audit["style_metrics"] = asdict(report.metrics)
    audit["style_flagged"] = [verdict.metric for verdict in report.flagged]

    if not report.thresholds_present:
        console.print(
            "[dim]style: no THRESHOLDS block in canon/style-guide.md — "
            "measured, nothing judged.[/dim]"
        )
    elif report.flagged:
        names = ", ".join(verdict.metric for verdict in report.flagged)
        console.print(
            f"[yellow]style[/yellow] outside band: {names} (advisory; "
            f"check-style --book {config.slug} --chapter "
            f"{entry.chapter_number} shows the numbers)"
        )
    else:
        console.print("[green]style[/green] every declared threshold met")


def _editorial_audit(
    result: EditorialResult,
    recorder: CallRecorder,
    applied: Reconciliation | None,
    refusal: str,
) -> dict[str, object]:
    """The review half of the session record (specs §13).

    Carries the raw validated delta, which is the only place a
    `progressed` thread note ever reaches the author (specs §12) — the
    reconciler deliberately writes those nowhere.
    """
    return {
        "status": result.status,
        "reason": result.reason or refusal,
        "repair_rounds": result.repair_rounds,
        "assigned_model": result.assigned_model,
        "actual_model": result.actual_model,
        "fallback_triggered": result.fallback_triggered,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "delta": result.delta.model_dump() if result.delta else None,
        "applied": None
        if applied is None
        else {
            "facts_added": applied.facts_added,
            "threads_opened": applied.threads_opened,
            "threads_resolved": applied.threads_resolved,
            "questions_added": applied.questions_added,
            "summary_added": applied.summary_added,
        },
        "calls": recorder.as_audit_list(),
    }


def _report_violations(console: Console, result: EditorialResult) -> None:
    """OQ-10: never phrase this as a guarantee, in either direction."""
    violations = result.delta.continuity_violations if result.delta else []
    if violations:
        console.print(f"[yellow]continuity[/yellow] {len(violations)} reported:")
        for violation in violations:
            console.print(f"  [{violation.severity}] {violation.violated_fact}")
            console.print(f"    chapter says: {violation.chapter_excerpt}")
    else:
        console.print(
            "[dim]continuity: none reported. Advisory only — bare number "
            "disagreements are the one class proven caught (OQ-10); an "
            "empty list is not proof of a clean chapter.[/dim]"
        )


def _complete(
    config: BookConfig,
    entry: ChapterEntry,
    machine: SessionStateMachine,
    *,
    session_id: str,
    audit: dict[str, object],
    note: str | None,
    console: Console,
) -> int:
    """The `complete` phase: chapter status flipped, pointer advanced."""
    path = chapter_path(config.root, entry.chapter_number)
    fields, _ = split_chapter_file(path.read_text(encoding="utf-8"))
    if fields.get("status") == "draft":
        flip_chapter_status(
            config.root,
            entry.chapter_number,
            "pending-review",
            expected_current="draft",
        )

    manifest = parse_manifest(
        (config.root / "canon" / "plot-outline.md").read_text(encoding="utf-8")
    )
    try:
        upcoming = resolve_target(manifest, None)
        next_chapter, next_pov = upcoming.chapter_number, upcoming.pov
    except ConfigError:
        next_chapter, next_pov = entry.chapter_number, entry.pov
        console.print(
            "[dim]no planned rows left in the manifest — the pointer stays "
            "on this chapter until one is added.[/dim]"
        )

    machine.transition(
        "complete",
        session_id=session_id,
        status="pending-review",
        chapter=next_chapter,
        pov=next_pov,
        # specs §12: the delta's next_step_note is the prose half of the
        # pointer. It is model text about what happens next, never canon.
        note=note,
    )
    audit_path = _end_session(config, session_id, audit, "complete")
    console.print(f"audit:    {audit_path}")
    console.print(
        f"[green]complete[/green] ch-{entry.chapter_number:03d} is "
        f"pending-review; next up is chapter {next_chapter:03d} "
        f"({next_pov})."
    )
    return 0


def _review(
    config: BookConfig,
    entry: ChapterEntry,
    machine: SessionStateMachine,
    providers: dict[str, Provider],
    *,
    session_id: str,
    audit: dict[str, object],
    console: Console,
) -> int:
    """styled -> [editorial-pending | reconciled] -> complete (specs §11).

    Every phase is on disk before the next one starts, so any exit here is
    resumable with --resume.
    """
    path = chapter_path(config.root, entry.chapter_number)
    fields, body = split_chapter_file(path.read_text(encoding="utf-8"))
    note: str | None = None

    if machine.phase == "drafted":
        _style_phase(
            config,
            entry,
            machine,
            body,
            fields.get("target_words"),
            session_id=session_id,
            audit=audit,
            console=console,
        )

    if machine.phase == "styled" and not config.pipeline.editorial.enabled:
        # Decision #36: the one route to 'complete' that writes no canon.
        console.print(
            "[yellow]editorial disabled[/yellow] config/pipeline.yaml sets "
            "editorial.enabled: false — no continuity review ran, and canon "
            "was not touched."
        )
        return _complete(
            config,
            entry,
            machine,
            session_id=session_id,
            audit=audit,
            note=None,
            console=console,
        )

    if machine.phase in ("styled", "editorial-pending"):
        recorder = CallRecorder()
        result = run_editorial_pass(
            config, entry, body, providers, on_attempt=recorder.record
        )

        applied: Reconciliation | None = None
        refusal = ""
        if result.status == "validated":
            assert result.delta is not None
            try:
                applied = reconcile(config, result.delta, session_id=session_id)
            except (EditorialError, VaultError) as exc:
                refusal = str(exc)

        audit["editorial"] = _editorial_audit(result, recorder, applied, refusal)

        if applied is None:
            machine.transition(
                "editorial-pending",
                session_id=session_id,
                status="editorial-pending",
            )
            audit_path = _end_session(config, session_id, audit, "editorial-pending")
            console.print(
                f"[yellow]editorial-pending[/yellow] {refusal or result.reason}"
            )
            console.print(f"audit:    {audit_path}")
            # The reason string already says canon is untouched; repeating
            # it here would bury the one line that says what to do next.
            console.print(f"Retry:    write-session --book {config.slug} --resume")
            return EXIT_EDITORIAL_PENDING

        machine.transition("reconciled", session_id=session_id, status="reconciled")
        note = result.delta.next_step_note if result.delta else None
        console.print(
            f"[green]reconciled[/green] {applied.canon_lines_added} canon "
            f"line(s) appended via {result.actual_model}"
        )
        if applied.threads_resolved:
            console.print(f"threads resolved: {', '.join(applied.threads_resolved)}")
        if applied.patches_path:
            console.print(f"suggested patches: {applied.patches_path}")
        _report_violations(console, result)

    return _complete(
        config,
        entry,
        machine,
        session_id=session_id,
        audit=audit,
        note=note,
        console=console,
    )


def run_session(
    book_slug: str,
    vault_root: Path,
    env,
    *,
    chapter: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    resume: bool = False,
    providers: dict[str, Provider] | None = None,
    console: Console | None = None,
) -> int:
    console = console or Console()
    config = load_book_config(vault_root, book_slug, env=env)
    machine = SessionStateMachine.load(config.root)
    pointer = machine.current

    if machine.is_blocked:
        console.print(
            f"[red]blocked[/red] {pointer.blocked_reason or 'no reason recorded'}"
        )
        console.print(
            "Fix the blocker, then clear `blocked:` in log/next-step.md. Nothing ran."
        )
        return 1

    # A pointer that has not reached 'complete' owns the target: the
    # manifest cannot supply it, because drafting already flipped the row
    # to 'written' and next_target() would skip straight past the chapter
    # whose editorial pass never finished.
    mid_flight = machine.phase != "complete"
    # 'target' is mid-flight but has produced nothing: the session that
    # recorded it never got a draft onto disk (an all-routes-exhausted run
    # leaves the phase here). There is no work to resume, so the refusal
    # below would send the author to --resume, which would then refuse for
    # the stub on disk and point at --force. The exists check already gives
    # that answer directly.
    interrupted = machine.phase not in ("complete", "target")
    override = (
        chapter
        if chapter is not None
        else (pointer.next_chapter if mid_flight else None)
    )
    entry = resolve_target(config.manifest, override)

    if resume and not interrupted:
        if machine.phase == "target":
            # An all-routes-exhausted run leaves the phase here with a
            # stub on disk and nothing to continue.
            console.print(
                "[red]nothing to resume[/red] the recorded session never "
                "produced a draft. Re-run without --resume; add --force if a "
                "failed-stub chapter is still on disk."
            )
        else:
            console.print(
                "[red]nothing to resume[/red] the last session reached "
                "'complete'. Re-run without --resume to start the next chapter."
            )
        return 1
    if interrupted and entry.chapter_number != pointer.next_chapter:
        console.print(
            f"[red]refusing[/red] log/next-step.md records chapter "
            f"{pointer.next_chapter:03d} at phase '{machine.phase}'. Finish "
            f"that session before starting chapter {entry.chapter_number:03d}."
        )
        return 1
    if interrupted and not (resume or force):
        return _resume_refusal(console, book_slug, machine, entry)

    resuming = resume and machine.phase in DRAFT_DONE_PHASES

    path = chapter_path(config.root, entry.chapter_number)
    if path.exists() and not resuming:
        if not force:
            console.print(
                f"[red]refusing[/red] {path} already exists. "
                "Re-run with --force to replace it."
            )
            return 1
        if not _confirm_overwrite(console, path):
            console.print("[red]aborted[/red] — no confirmation, no overwrite.")
            return 1
    if resuming and not path.exists():
        console.print(
            f"[red]pointer disagrees with disk[/red] phase is "
            f"'{machine.phase}' but {path} does not exist. Re-run with "
            "--force to draft it again."
        )
        return 1

    if dry_run and resuming:
        console.print(
            f"[yellow]nothing to assemble[/yellow] chapter "
            f"{entry.chapter_number:03d} is already drafted (phase "
            f"'{machine.phase}'); resuming runs the review phases, which "
            "send no drafting prompt."
        )
        return 0

    assembled = build_prompt(config, entry.chapter_number)

    if dry_run:
        # Plain print, not rich markup: the output must be diffable and
        # pasteable without ANSI artefacts.
        print(assembled.text)
        return 0

    if providers is None:
        from novel_engine.providers import build_providers

        providers = build_providers(env)

    session_id = make_session_id()

    # OQ-01 / ADR-0013: a session that writes canon needs somewhere to
    # undo it from. Everything above this line is a refusal or a dry-run
    # and has written nothing, so this is the last moment before the
    # first write.
    snapshots = ensure_repo(config.root)
    if snapshots.active:
        author_edits = snapshot(
            config.root, f"author edits before session {session_id}"
        )
        if author_edits:
            console.print(
                f"[dim]snapshot {author_edits} — your edits since the last "
                "session, committed before this one starts.[/dim]"
            )
    elif snapshots.externally_tracked:
        console.print(f"[dim]snapshots: {snapshots.reason}[/dim]")
    elif config.pipeline.editorial.enabled:
        # Refusing is the whole point of OQ-01: canon writes with no
        # recovery path are the failure this project must not ship.
        console.print(f"[red]no recovery path[/red] {snapshots.reason}")
        console.print("Nothing ran; no prose and no canon were touched.")
        return 1
    else:
        console.print(
            f"[yellow]no snapshots[/yellow] {snapshots.reason} Continuing "
            "because editorial is disabled, so this session writes no canon."
        )

    audit: dict[str, object] = {
        "session_id": session_id,
        "book_slug": config.slug,
        "chapter_number": entry.chapter_number,
        "pov": entry.pov,
        "beat": entry.beat,
        "resumed": resuming,
        "snapshots": snapshots.active,
    }

    if resuming:
        console.print(
            f"[cyan]resuming[/cyan] ch-{entry.chapter_number:03d} from phase "
            f"'{machine.phase}' — the prose on disk is not touched."
        )
    else:
        if force and machine.phase in DRAFT_DONE_PHASES:
            # The author asked to replace the prose, which abandons the
            # session that produced it (decision #38).
            machine.restart(
                chapter=entry.chapter_number, pov=entry.pov, session_id=session_id
            )
        else:
            machine.transition(
                "target",
                session_id=session_id,
                chapter=entry.chapter_number,
                pov=entry.pov,
                status="drafting",
            )

        recorder = CallRecorder()
        result = draft_chapter(
            config,
            entry,
            assembled.text,
            providers,
            session_id=session_id,
            allow_overwrite=force,
            on_attempt=recorder.record,
        )

        audit.update(_draft_audit(assembled, result))

        if result.status == "failed-stub":
            # Phase stays 'target': nothing was drafted, so the next run
            # must draft, not review.
            _end_session(config, session_id, audit, result.status)
            console.print(
                f"[red]all routes exhausted[/red] — wrote failed-stub marker to "
                f"{result.path}. Manifest untouched (stays planned); re-run with "
                "--force once providers recover."
            )
            return 1

        machine.transition("drafted", session_id=session_id, status="draft")

        console.print(
            f"[green]drafted[/green] ch-{result.chapter_number:03d} "
            f"({result.actual_words} words) via {result.actual_model}"
        )
        if result.fallback_triggered:
            console.print(
                f"[yellow]fallback fired[/yellow] — assigned "
                f"{result.assigned_model}, served by {result.actual_model}"
            )
        if result.continuation_rounds:
            console.print(f"continuation rounds: {result.continuation_rounds}")
        console.print(f"chapter:  {result.path}")

    return _review(
        config,
        entry,
        machine,
        providers,
        session_id=session_id,
        audit=audit,
        console=console,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="write-session",
        description="Draft one chapter for a book (one chapter per session).",
    )
    parser.add_argument("--book", required=True, help="Book slug (kebab-case).")
    parser.add_argument(
        "--chapter",
        type=int,
        default=None,
        help="Override manifest target selection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the assembled prompt and exit before any API call.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an interrupted session from its recorded phase.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permit replacing an existing chapter (asks for confirmation).",
    )
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path("vault"),
        help="Vault root directory (default: vault/).",
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv()

    try:
        return run_session(
            args.book,
            args.vault_root,
            os.environ,
            chapter=args.chapter,
            dry_run=args.dry_run or os.environ.get("DRY_RUN") == "1",
            force=args.force,
            resume=args.resume,
        )
    except NovelEngineError as exc:
        Console(stderr=True).print(f"[red]error[/red] {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
