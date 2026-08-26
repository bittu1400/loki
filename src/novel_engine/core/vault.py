"""Markdown and frontmatter IO; safe append primitives.

THE ONE-WRITER RULE: this is the only module in the project permitted to
write to disk. Everything else returns data. Exposes append primitives
only — append_fact, append_summary, append_thread, flip_thread_status —
and deliberately no general "write canon file" function (invariant 1).

Phase 3 additions, same rule: write_chapter (create-only chapter file)
and flip_manifest_status (the single permitted mechanical edit to
plot-outline.md — the status field of one row, nothing else).
"""

from __future__ import annotations

import hashlib
import re
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from novel_engine.core.config import SLUG_PATTERN
from novel_engine.core.errors import ConfigError, VaultError
from novel_engine.core.outline import (
    LEGAL_STATUSES,
    MANIFEST_BEGIN,
    MANIFEST_END,
)

CHAPTER_FILE = re.compile(r"^chapter-(\d{3,4})\.md$")


def scaffold_book(vault_root: Path | str, slug: str) -> Path:
    """Create vault/<slug>/ from the packaged templates and return its root.

    A scaffolder, not an interview (ADR-0001). Refuses to overwrite an
    existing book directory.
    """
    if not SLUG_PATTERN.fullmatch(slug):
        raise ConfigError(
            f"Book slug {slug!r} is not valid. Use lowercase letters, digits, "
            "and hyphens (e.g. 'the-salt-almanac')."
        )

    vault = Path(vault_root).resolve()
    root = (vault / slug).resolve()
    if root.parent != vault:
        raise ConfigError(
            f"Book path {root} does not resolve directly under {vault}; "
            "refusing to write outside the vault root."
        )
    if root.exists():
        raise ConfigError(
            f"Refusing to overwrite existing book directory: {root}. "
            "Pick another slug or remove the directory yourself."
        )

    templates = resources.files("novel_engine") / "templates" / "book"
    with resources.as_file(templates) as source:
        shutil.copytree(source, root)

    return root


# --- chapters ---------------------------------------------------------------


def generated_hash(body: str) -> str:
    """Hash of the body AS GENERATED — the frontmatter convention.

    SHA-256 of everything after the frontmatter, leading blank lines
    stripped, prefixed `sha256:`. Deliberately immutable: recomputing it
    against a later-edited file is how an author edit is detected
    (specs.md §3), so it must never be refreshed.
    """
    digest = hashlib.sha256(body.lstrip("\n").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def chapter_path(book_root: Path, chapter_number: int) -> Path:
    return book_root / "chapters" / f"chapter-{chapter_number:03d}.md"


def split_chapter_file(text: str) -> tuple[dict[str, Any], str]:
    """(frontmatter fields, body-as-after-frontmatter) for a chapter file."""
    if not text.startswith("---\n"):
        raise VaultError("Chapter file does not start with frontmatter ('---').")
    end = text.find("\n---", 4)
    if end == -1:
        raise VaultError("Chapter frontmatter is not closed by a '---' line.")
    fields = yaml.safe_load(text[4:end])
    body = text[text.find("\n", end + 1) + 1 :]
    return (fields or {}), body


def write_chapter(
    book_root: Path,
    chapter_number: int,
    fields: dict[str, Any],
    body: str,
    *,
    allow_overwrite: bool = False,
) -> Path:
    """Create chapters/chapter-NNN.md. The only way a chapter is written.

    - Refuses to touch an existing file unless the caller passes
      `allow_overwrite` — which cli/ code may set only behind --force
      plus explicit confirmation. The engine never overwrites
      author-written prose on its own (invariant 5).
    - Computes and owns `generated_hash`; callers must not supply it.
    - Creates the file exclusively (O_EXCL semantics via mode "x") so a
      race cannot half-overwrite.
    """
    path = chapter_path(book_root, chapter_number)
    if path.exists() and not allow_overwrite:
        raise VaultError(
            f"Refusing to overwrite existing chapter: {path}. "
            "Re-run with --force to replace it."
        )
    if "generated_hash" in fields:
        raise VaultError(
            "Callers must not supply generated_hash; the writing primitive "
            "computes it from the body as generated (specs.md §3)."
        )
    if not path.parent.is_dir():
        raise VaultError(f"Missing chapters directory: {path.parent}.")

    # Hash the EXACT bytes that will sit after the frontmatter on disk,
    # including the trailing newline — not the caller's pre-normalised
    # string — or post-write verification would fail by construction.
    stored_body = body.rstrip() + "\n"

    frontmatter = yaml.safe_dump(
        {**fields, "generated_hash": generated_hash(stored_body)},
        sort_keys=False,
        allow_unicode=True,
        width=10_000,
    ).rstrip("\n")
    text = f"---\n{frontmatter}\n---\n\n{stored_body}"

    try:
        # Mode "x" gives O_EXCL semantics: a race cannot half-overwrite.
        # Only an explicit allow_overwrite call may open with "w".
        with path.open("w" if allow_overwrite else "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise VaultError(f"{path} appeared mid-write; refusing to clobber it.") from exc

    # Verify what landed on disk hashes back to the recorded value.
    written_fields, written_body = split_chapter_file(path.read_text(encoding="utf-8"))
    if written_fields.get("generated_hash") != generated_hash(written_body):
        raise VaultError(
            f"Post-write verification failed for {path}: hash on disk does "
            "not match its own body. Remove the file and re-run."
        )
    return path


# --- manifest ---------------------------------------------------------------


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def flip_manifest_status(
    book_root: Path,
    chapter_number: int,
    new_status: str,
    expected_current: str | None = None,
) -> None:
    """The single permitted mechanical edit to plot-outline.md.

    Rewrites exactly one cell — the `status` of one manifest row — and
    nothing else; every other byte of the file is preserved verbatim.
    Fails closed: unknown chapter, illegal status, or a current status
    that does not match `expected_current` aborts before any write.
    """
    if new_status not in LEGAL_STATUSES:
        legal = ", ".join(sorted(LEGAL_STATUSES))
        raise VaultError(f"Illegal manifest status {new_status!r}; legal: {legal}.")

    outline_path = book_root / "canon" / "plot-outline.md"
    text = outline_path.read_text(encoding="utf-8")
    begin = text.count(MANIFEST_BEGIN)
    end = text.count(MANIFEST_END)
    if begin != 1 or end != 1:
        raise VaultError(
            f"{outline_path} must contain exactly one {MANIFEST_BEGIN} and "
            f"one {MANIFEST_END}; found {begin} and {end}."
        )
    pre, rest = text.split(MANIFEST_BEGIN, 1)
    section, post = rest.split(MANIFEST_END, 1)
    lines = section.splitlines()

    status_index: int | None = None
    header_cells: list[str] | None = None
    target_line_index: int | None = None
    current_status: str | None = None

    for index, line in enumerate(lines):
        cells = _split_row(line)
        if header_cells is None and "chapter" in cells and "status" in cells:
            header_cells = cells
            status_index = cells.index("status")
            continue
        if header_cells is None or len(cells) != len(header_cells) or not cells:
            continue
        first = cells[0]
        if not first.isdigit() or int(first) != chapter_number:
            continue
        if target_line_index is not None:
            raise VaultError(
                f"{outline_path}: duplicate manifest rows for chapter "
                f"{chapter_number}; refusing to guess."
            )
        target_line_index = index
        current_status = cells[status_index]

    if target_line_index is None or header_cells is None:
        raise VaultError(
            f"{outline_path}: chapter {chapter_number} has no data row in "
            "the manifest section."
        )

    if expected_current is not None and current_status != expected_current:
        raise VaultError(
            f"{outline_path}: chapter {chapter_number} has status "
            f"{current_status!r}, expected {expected_current!r}. "
            "Refusing the flip."
        )

    old_cells = _split_row(lines[target_line_index])
    old_line = lines[target_line_index]
    parts = old_line.split("|")
    parts[status_index + 1] = f" {new_status} "
    new_line = "|".join(parts)
    if section.count(old_line) != 1:
        raise VaultError(
            f"{outline_path}: manifest row for chapter {chapter_number} is "
            "not unique inside the manifest section; refusing to splice."
        )
    new_section = section.replace(old_line, new_line, 1)
    new_text = pre + MANIFEST_BEGIN + new_section + MANIFEST_END + post

    # Verify: exactly one line differs, and at cell level only the status
    # cell changed.
    differing = [
        (old, new)
        for old, new in zip(text.splitlines(), new_text.splitlines(), strict=True)
        if old != new
    ]
    expected_cells = [
        cell if i != status_index else new_status for i, cell in enumerate(old_cells)
    ]
    if len(differing) != 1 or _split_row(differing[0][1]) != expected_cells:
        raise VaultError(
            f"{outline_path}: reconstruction changed more than the status "
            "cell. Refusing to write."
        )

    outline_path.write_text(new_text, encoding="utf-8")
