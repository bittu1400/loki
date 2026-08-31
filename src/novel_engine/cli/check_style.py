"""`check-style` — deterministic style checks over one existing chapter.

Costs nothing and needs no API key: it reads a chapter off disk, measures
it, and compares the numbers against whatever thresholds the book itself
declares. It deliberately does NOT go through load_book_config, which
validates provider keys — a measurement pass must run on a machine with
no keys at all.

Exit codes follow specs §15: 0 whenever the chapter was measured, even
when metrics are out of band. Verdicts are advisory (specs §14); only a
real error — missing chapter, malformed thresholds — exits 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from novel_engine.core.errors import NovelEngineError, VaultError
from novel_engine.core.vault import chapter_path, split_chapter_file
from novel_engine.quality.style_checks import StyleReport, build_report

STATUS_STYLE = {"ok": "green", "low": "yellow", "high": "yellow"}


def _render(console: Console, report: StyleReport) -> None:
    metrics = report.metrics
    verdicts = {verdict.metric: verdict for verdict in report.verdicts}

    console.print(
        f"[bold]{report.book_slug}[/bold] chapter "
        f"{report.chapter_number:03d} — {metrics.word_count} words, "
        f"{metrics.sentence_count} sentences, "
        f"{metrics.paragraph_count} paragraphs"
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_column("band", justify="right")
    table.add_column("", justify="left")

    for name, value, form in (
        ("sentence_length_mean", metrics.sentence_length_mean, "{:.1f}"),
        ("sentence_length_stdev", metrics.sentence_length_stdev, "{:.1f}"),
        ("adverb_rate_per_1000", metrics.adverb_rate_per_1000, "{:.1f}"),
        ("type_token_ratio", metrics.type_token_ratio, "{:.3f}"),
        ("dialogue_ratio", metrics.dialogue_ratio, "{:.3f}"),
        ("em_dash_rate_per_1000", metrics.em_dash_rate_per_1000, "{:.1f}"),
        ("semicolon_rate_per_1000", metrics.semicolon_rate_per_1000, "{:.1f}"),
        ("paragraph_length_mean", metrics.paragraph_length_mean, "{:.1f}"),
        ("paragraph_length_max", float(metrics.paragraph_length_max), "{:.0f}"),
        ("words_vs_target", metrics.words_vs_target, "{:.2f}"),
    ):
        verdict = verdicts.get(name)
        band = "—"
        if verdict is not None:
            low = "—" if verdict.minimum is None else f"{verdict.minimum:g}"
            high = "—" if verdict.maximum is None else f"{verdict.maximum:g}"
            band = f"{low}..{high}"
        status = verdict.status if verdict else ""
        table.add_row(
            name,
            "—" if value is None else form.format(value),
            band,
            f"[{STATUS_STYLE.get(status, 'dim')}]{status}[/]" if status else "",
        )
    console.print(table)

    if metrics.banned_phrase_hits:
        console.print("[yellow]banned phrases[/yellow]")
        for phrase, count in metrics.banned_phrase_hits.items():
            console.print(f"  {count}x  {phrase}")

    openings = list(metrics.repeated_openings.items())[:5]
    if openings:
        joined = ", ".join(f"{word} x{count}" for word, count in openings)
        console.print(f"[dim]repeated openings[/dim] {joined}")

    if not report.thresholds_present:
        console.print(
            "[dim]no THRESHOLDS block in canon/style-guide.md — metrics "
            "reported, verdicts skipped.[/dim]"
        )
    elif report.flagged:
        names = ", ".join(verdict.metric for verdict in report.flagged)
        console.print(f"[yellow]outside band[/yellow] {names} (advisory)")
    else:
        console.print("[green]every declared threshold met[/green]")


def check_style(
    book_slug: str,
    chapter: int,
    vault_root: Path,
    console: Console | None = None,
) -> int:
    console = console or Console()
    path = chapter_path(vault_root / book_slug, chapter)
    if not path.exists():
        raise VaultError(f"{path} does not exist — nothing to measure.")

    fields, body = split_chapter_file(path.read_text(encoding="utf-8"))
    style_guide = vault_root / book_slug / "canon" / "style-guide.md"
    if not style_guide.exists():
        raise VaultError(f"{style_guide} does not exist — no banned phrases to check.")

    report = build_report(
        book_slug,
        chapter,
        body,
        style_guide.read_text(encoding="utf-8"),
        target_words=fields.get("target_words"),
        style_guide_path=style_guide,
    )
    _render(console, report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-style",
        description="Deterministic style metrics for one existing chapter.",
    )
    parser.add_argument("--book", required=True, help="Book slug (kebab-case).")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number.")
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path("vault"),
        help="Vault root directory (default: vault/).",
    )
    args = parser.parse_args(argv)

    try:
        return check_style(args.book, args.chapter, args.vault_root)
    except NovelEngineError as exc:
        Console(stderr=True).print(f"[red]error[/red] {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
