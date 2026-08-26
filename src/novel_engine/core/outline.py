"""Chapter-manifest parsing and next-target selection.

Only content strictly between the MANIFEST markers is parsed; everything
else in plot-outline.md is prose for humans and the model, never for the
parser (specs.md §2). Chapter numbers come from this manifest, never from
counting files in chapters/.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from novel_engine.core.errors import ConfigError

MANIFEST_BEGIN = "<!-- MANIFEST:BEGIN -->"
MANIFEST_END = "<!-- MANIFEST:END -->"

LEGAL_STATUSES = {"planned", "drafting", "written", "revised"}
REQUIRED_COLUMNS = ("chapter", "pov", "arc", "status", "beat")


class ManifestError(ConfigError):
    """The chapter manifest in plot-outline.md is malformed."""


class ChapterEntry(BaseModel):
    chapter_number: int
    pov: str
    arc: str
    status: str
    beat: str


def _extract_manifest_section(text: str) -> str:
    begin = text.count(MANIFEST_BEGIN)
    end = text.count(MANIFEST_END)
    if begin != 1 or end != 1:
        raise ManifestError(
            f"plot-outline.md must contain exactly one {MANIFEST_BEGIN} and "
            f"one {MANIFEST_END} marker; found {begin} and {end}."
        )
    section = text.split(MANIFEST_BEGIN, 1)[1].split(MANIFEST_END, 1)[0]
    if not section.strip():
        raise ManifestError(
            "The manifest section between the MANIFEST markers is empty. "
            "Add a table row per chapter."
        )
    return section


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_manifest(text: str) -> list[ChapterEntry]:
    """Parse the controlled manifest section into chapter entries."""
    section = _extract_manifest_section(text)
    lines = [line for line in section.splitlines() if line.strip()]
    header = [column.lower() for column in _split_table_row(lines[0])]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise ManifestError(
            f"Manifest table is missing required column(s): {', '.join(missing)}. "
            f"Required columns are {', '.join(REQUIRED_COLUMNS)}; extra columns "
            "are permitted and ignored."
        )
    if len(lines) < 2:
        raise ManifestError(
            "Manifest table is missing its markdown separator row "
            "(the |---|---| line directly under the header)."
        )
    separator = _split_table_row(lines[1])
    if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in separator):
        raise ManifestError(
            "Manifest table is missing its markdown separator row "
            "(the |---|---| line directly under the header)."
        )
    lines = lines[:1] + lines[2:]

    entries: list[ChapterEntry] = []
    for raw_line in lines[1:]:
        cells = _split_table_row(raw_line)
        if len(cells) != len(header):
            raise ManifestError(
                f"Manifest row has {len(cells)} cells but the header has "
                f"{len(header)}: {raw_line!r}"
            )
        row = dict(zip(header, cells, strict=True))
        if not row["chapter"].isdigit():
            raise ManifestError(
                f"Manifest chapter value {row['chapter']!r} is not a number."
            )
        status = row["status"]
        if status not in LEGAL_STATUSES:
            legal = ", ".join(sorted(LEGAL_STATUSES))
            raise ManifestError(
                f"Chapter {row['chapter']} has status {status!r}; "
                f"legal statuses are: {legal}."
            )
        entries.append(
            ChapterEntry(
                chapter_number=int(row["chapter"]),
                pov=row["pov"],
                arc=row["arc"],
                status=status,
                beat=row["beat"],
            )
        )

    numbers = [entry.chapter_number for entry in entries]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        raise ManifestError(
            f"Duplicate chapter number(s) in manifest: "
            f"{', '.join(map(str, duplicates))}. Abort rather than guess."
        )
    return entries


def next_target(entries: list[ChapterEntry]) -> int:
    """Lowest chapter number with status `planned`.

    Aborts on non-contiguous numbering rather than guessing (specs.md §2).
    """
    planned = [entry for entry in entries if entry.status == "planned"]
    if not planned:
        raise ConfigError(
            "No chapter with status 'planned' in the manifest. Add a row or "
            "flip a status to plan the next chapter."
        )
    target = min(entry.chapter_number for entry in planned)
    known = {entry.chapter_number for entry in entries}
    gaps = [n for n in range(1, max(known)) if n not in known]
    if gaps:
        raise ConfigError(
            "Manifest chapter numbering is non-contiguous; missing: "
            f"{', '.join(map(str, gaps))}. Fix the manifest before running."
        )
    return target


def resolve_target(
    entries: list[ChapterEntry], override: int | None = None
) -> ChapterEntry:
    """The manifest row to draft this session.

    `override` (the CLI's --chapter) must name an existing manifest row —
    it selects, never invents. Without an override, next_target() decides.
    """
    if override is not None:
        for entry in entries:
            if entry.chapter_number == override:
                return entry
        known = ", ".join(str(e.chapter_number) for e in entries)
        raise ConfigError(
            f"Requested chapter {override} is not in the manifest "
            f"(manifest chapters: {known}). Chapter numbers come from "
            "the manifest, never from the filesystem."
        )
    target = next_target(entries)
    return next(e for e in entries if e.chapter_number == target)
