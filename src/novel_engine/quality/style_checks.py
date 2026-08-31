"""Threshold parsing and the style report (specs §14, decisions.md #22).

Thresholds are the author's, not the engine's: they live in a book's
`canon/style-guide.md` between THRESHOLDS markers, parsed with the same
discipline as MANIFEST and FACTS. There are NO built-in numeric defaults.
A book with no block gets its metrics reported and every verdict skipped
— "not tuned yet" stays a visible state instead of a hidden default.

Verdicts are advisory. Nothing here blocks a chapter (specs §14); a
metric outside its band is evidence for the author and the editorial
pass, never a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path

from novel_engine.core.context_builder import banned_phrases
from novel_engine.core.errors import NovelEngineError
from novel_engine.quality.metrics import ChapterMetrics, compute_metrics

THRESHOLDS_BEGIN = "<!-- THRESHOLDS:BEGIN -->"
THRESHOLDS_END = "<!-- THRESHOLDS:END -->"

#: An unbounded cell: empty, or a dash the author wrote to mean "no bound".
UNBOUNDED = {"", "-", "\u2013", "\u2014", "none", "any"}  # hyphen, en, em

SEPARATOR_ROW = re.compile(r"^\|[\s|:-]+\|$")

#: Metrics a threshold may name — the scalar ones. The collection-valued
#: metrics (banned_phrase_hits, repeated_openings, paragraph_lengths) are
#: reported, never banded: "how many is too many" is a reading judgement.
COMPARABLE_METRICS = frozenset(
    field.name
    for field in fields(ChapterMetrics)
    if not field.type.startswith(("list", "dict")) and field.name != "target_words"
)


class StyleCheckError(NovelEngineError):
    """A thresholds block exists but cannot be trusted to mean anything."""


@dataclass(frozen=True)
class Threshold:
    """One metric's allowed band. Either bound may be absent."""

    metric: str
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True)
class Verdict:
    """One metric measured against its band. `status` is advisory only."""

    metric: str
    value: float
    minimum: float | None
    maximum: float | None
    status: str  # ok | low | high


@dataclass(frozen=True)
class StyleReport:
    """Metrics for one chapter, plus verdicts if the book declared any."""

    book_slug: str
    chapter_number: int
    metrics: ChapterMetrics
    verdicts: list[Verdict]
    thresholds_present: bool

    @property
    def flagged(self) -> list[Verdict]:
        return [verdict for verdict in self.verdicts if verdict.status != "ok"]


def _cell_bound(cell: str, metric: str, side: str, path: Path) -> float | None:
    text = cell.strip().strip("`")
    if text.lower() in UNBOUNDED:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise StyleCheckError(
            f"{path}: THRESHOLDS row '{metric}' has a non-numeric {side} "
            f"bound ({cell.strip()!r}). Use a number, or '-' for unbounded."
        ) from exc


def parse_thresholds(
    style_guide_text: str, path: Path | None = None
) -> dict[str, Threshold]:
    """Thresholds declared between the markers; `{}` when there is no block.

    Absence is legitimate and silent — the book has simply not been tuned.
    A block that IS present but malformed raises: a threshold the author
    believes is active but which silently does nothing is worse than none.
    """
    path = path or Path("canon/style-guide.md")
    if THRESHOLDS_BEGIN not in style_guide_text:
        return {}

    start = style_guide_text.index(THRESHOLDS_BEGIN) + len(THRESHOLDS_BEGIN)
    end = style_guide_text.find(THRESHOLDS_END, start)
    if end == -1:
        raise StyleCheckError(
            f"{path}: {THRESHOLDS_BEGIN} has no matching {THRESHOLDS_END}."
        )

    thresholds: dict[str, Threshold] = {}
    for line in style_guide_text[start:end].splitlines():
        row = line.strip()
        if not row.startswith("|") or SEPARATOR_ROW.match(row):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if cells[:1] == ["metric"]:
            continue
        if len(cells) != 3:
            raise StyleCheckError(
                f"{path}: THRESHOLDS row {row!r} does not have exactly three "
                "cells (metric | min | max)."
            )
        metric = cells[0].strip("`")
        if metric not in COMPARABLE_METRICS:
            raise StyleCheckError(
                f"{path}: THRESHOLDS names unknown metric {metric!r}. "
                f"Bandable metrics: {', '.join(sorted(COMPARABLE_METRICS))}."
            )
        if metric in thresholds:
            raise StyleCheckError(f"{path}: THRESHOLDS lists {metric!r} twice.")
        minimum = _cell_bound(cells[1], metric, "min", path)
        maximum = _cell_bound(cells[2], metric, "max", path)
        if minimum is None and maximum is None:
            raise StyleCheckError(
                f"{path}: THRESHOLDS row {metric!r} bounds nothing. Give it a "
                "min, a max, or delete the row."
            )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise StyleCheckError(
                f"{path}: THRESHOLDS row {metric!r} has min {minimum} above "
                f"max {maximum}."
            )
        thresholds[metric] = Threshold(metric, minimum, maximum)
    return thresholds


def judge(metrics: ChapterMetrics, thresholds: dict[str, Threshold]) -> list[Verdict]:
    """One verdict per declared threshold, in declaration order.

    A metric whose value is None (an unset `words_vs_target`) is skipped:
    there is nothing to compare, and inventing a target would be a
    threshold decision the author did not make.
    """
    verdicts: list[Verdict] = []
    for metric, threshold in thresholds.items():
        value = getattr(metrics, metric)
        if value is None:
            continue
        status = "ok"
        if threshold.minimum is not None and value < threshold.minimum:
            status = "low"
        elif threshold.maximum is not None and value > threshold.maximum:
            status = "high"
        verdicts.append(
            Verdict(metric, float(value), threshold.minimum, threshold.maximum, status)
        )
    return verdicts


def build_report(
    book_slug: str,
    chapter_number: int,
    body: str,
    style_guide_text: str,
    target_words: int | None = None,
    style_guide_path: Path | None = None,
) -> StyleReport:
    """Measure one chapter body and judge it against its book's thresholds."""
    thresholds = parse_thresholds(style_guide_text, style_guide_path)
    metrics = compute_metrics(
        body,
        banned=banned_phrases(style_guide_text, style_guide_path),
        target_words=target_words,
    )
    return StyleReport(
        book_slug=book_slug,
        chapter_number=chapter_number,
        metrics=metrics,
        verdicts=judge(metrics, thresholds),
        thresholds_present=bool(thresholds),
    )


def main() -> None:
    """check-style entry point; CLI wiring is Phase 4 Batch 3."""
    raise NotImplementedError("check-style CLI arrives in Phase 4 Batch 3")
