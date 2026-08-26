"""Single-chapter session entry point (ADR-0003).

Assembles context, drafts one chapter through the provider chain, and
writes every artifact through core/vault.py. --dry-run prints the exact
assembled prompt and exits BEFORE any provider construction or API call,
because prompt tuning is the highest-iteration activity in the project
and free-tier quota is its hardest constraint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from rich.console import Console

from novel_engine.core.config import BookConfig, load_book_config
from novel_engine.core.context_builder import AssembledPrompt, build_prompt
from novel_engine.core.errors import NovelEngineError
from novel_engine.core.outline import resolve_target
from novel_engine.core.vault import chapter_path
from novel_engine.drafting.generate import DraftResult, draft_chapter, make_session_id
from novel_engine.providers.audit import CallRecorder
from novel_engine.providers.base import Provider

CONFIRM_WORD = "replace"


def _audit_payload(
    config: BookConfig, assembled: AssembledPrompt, result: DraftResult
) -> dict[str, object]:
    """specs.md §13: immutable, written once, no secrets."""
    return {
        "session_id": result.session_id,
        "book_slug": config.slug,
        "chapter_number": result.chapter_number,
        "pov": assembled.pov,
        "beat": assembled.beat,
        "final_phase": result.status,
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


def run_session(
    book_slug: str,
    vault_root: Path,
    env,
    *,
    chapter: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    providers: dict[str, Provider] | None = None,
    console: Console | None = None,
) -> int:
    console = console or Console()
    config = load_book_config(vault_root, book_slug, env=env)
    entry = resolve_target(config.manifest, chapter)

    path = chapter_path(config.root, entry.chapter_number)
    if path.exists():
        if not force:
            console.print(
                f"[red]refusing[/red] {path} already exists. "
                "Re-run with --force to replace it."
            )
            return 1
        if not _confirm_overwrite(console, path):
            console.print("[red]aborted[/red] — no confirmation, no overwrite.")
            return 1

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

    audit_path = config.root / "log" / "sessions" / f"{session_id}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(_audit_payload(config, assembled, result), indent=2),
        encoding="utf-8",
    )

    if result.status == "failed-stub":
        console.print(
            f"[red]all routes exhausted[/red] — wrote failed-stub marker to "
            f"{result.path}. Manifest untouched (stays planned); re-run with "
            "--force once providers recover."
        )
        return 1

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
    console.print(f"audit:    {audit_path}")
    return 0


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
        )
    except NovelEngineError as exc:
        Console(stderr=True).print(f"[red]error[/red] {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
