"""Markdown and frontmatter IO; safe append primitives.

THE ONE-WRITER RULE: this is the only module in the project permitted to
write to disk. Everything else returns data. Exposes append primitives
only — append_fact, append_thread, append_deepen_question,
append_summary, flip_thread_status — and deliberately no general "write
canon file" function (invariant 1).

Phase 3 additions, same rule: write_chapter (create-only chapter file)
and flip_manifest_status (the single permitted mechanical edit to
plot-outline.md — the status field of one row, nothing else).

Phase 6 addition: write_next_step (the single permitted overwrite primitive
for log/next-step.md — specs §8, architecture §3).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from novel_engine.core.config import SLUG_PATTERN
from novel_engine.core.context_builder import (
    FACTS_BEGIN,
    FACTS_END,
    parse_facts,
    recent_summaries,
)
from novel_engine.core.errors import ConfigError, VaultError
from novel_engine.core.outline import (
    LEGAL_STATUSES,
    MANIFEST_BEGIN,
    MANIFEST_END,
)
from novel_engine.core.state_machine import (
    NextStep,
    parse_next_step,
    serialize_next_step,
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


#: Chapter frontmatter statuses this engine may write. specs §11 also
#: defines `approved` and `published`; neither is reachable in v1
#: (ADR-0001), so neither is legal here yet. `failed-stub` is written by
#: write_chapter at creation and is never flipped — a stub is replaced
#: with --force, not promoted.
LEGAL_CHAPTER_STATUSES = frozenset({"draft", "pending-review"})

_STATUS_LINE = re.compile(
    r"^(?P<lead>status:[ \t]*)(?P<quote>[\"']?)(?P<value>[^\"'\n]*)(?P=quote)"
    r"(?P<trail>[ \t]*)$",
    re.MULTILINE,
)


def flip_chapter_status(
    book_root: Path,
    chapter_number: int,
    new_status: str,
    expected_current: str | None = None,
) -> None:
    """The single permitted mechanical edit to a chapter file (specs §3).

    Rewrites exactly one frontmatter cell — `status` — and nothing else.
    The BODY is never touched, which is why `generated_hash` survives:
    it hashes post-frontmatter bytes only, so a status flip cannot
    disturb the author-edit signal (decision #25, pitfalls B5).

    Fails closed: unknown chapter, illegal status, missing status key, or
    a current value that does not match `expected_current` aborts before
    any write.
    """
    if new_status not in LEGAL_CHAPTER_STATUSES:
        legal = ", ".join(sorted(LEGAL_CHAPTER_STATUSES))
        raise VaultError(f"Illegal chapter status {new_status!r}; legal: {legal}.")

    path = chapter_path(book_root, chapter_number)
    if not path.is_file():
        raise VaultError(f"Cannot flip status: {path} does not exist.")

    text = path.read_text(encoding="utf-8")
    fields, body_before = split_chapter_file(text)
    current = fields.get("status")
    if current is None:
        raise VaultError(f"{path} has no status key in its frontmatter.")
    if expected_current is not None and current != expected_current:
        raise VaultError(
            f"{path} status is {current!r}, expected {expected_current!r}; "
            "refusing to flip."
        )
    if current == new_status:
        return

    end = text.find("\n---", 4)
    frontmatter, rest = text[:end], text[end:]
    replaced, count = _STATUS_LINE.subn(
        lambda m: f"{m['lead']}{m['quote']}{new_status}{m['quote']}{m['trail']}",
        frontmatter,
        count=1,
    )
    if count != 1:
        raise VaultError(
            f"{path} frontmatter has no single editable status line; refusing to guess."
        )
    path.write_text(replaced + rest, encoding="utf-8")

    verified_fields, verified_body = split_chapter_file(
        path.read_text(encoding="utf-8")
    )
    if verified_fields.get("status") != new_status or verified_body != body_before:
        raise VaultError(
            f"Post-write verification failed for {path}: status flip did not "
            "land cleanly, or the body changed."
        )


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


# --- canon appends ----------------------------------------------------------
#
# Every primitive below adds ONE line inside a marker block (or one
# heading-and-paragraph, for summaries) and verifies its own write by
# reading the file back and parsing it. None of them can edit or delete
# an existing line, and none of them accepts a file body — that is
# invariant 1, expressed as an API rather than as a rule people remember.

THREADS_BEGIN = "<!-- THREADS:BEGIN -->"
THREADS_END = "<!-- THREADS:END -->"
QUEUE_BEGIN = "<!-- QUEUE:BEGIN -->"
QUEUE_END = "<!-- QUEUE:END -->"

#: `- `[T-NNN]` `[open|resolved:ch-NNN]` `[ch-NNN]` <thread>` (specs.md §5)
THREAD_LINE = re.compile(
    r"^- `\[(?P<thread_id>T-\d{3,})\]` "
    r"`\[(?P<status>open|resolved:ch-\d+)\]` "
    r"`\[ch-(?P<chapter>\d+)\]` "
    r"(?P<text>.+)$"
)
#: `- `[open|answered:YYYY-MM-DD]` `[ch-NNN]` <question>` (specs.md §6)
QUEUE_LINE = re.compile(
    r"^- `\[(?P<status>open|answered:\d{4}-\d{2}-\d{2})\]` "
    r"`\[ch-(?P<chapter>\d+)\]` "
    r"(?P<text>.+)$"
)


def _guard_line_text(value: str, field: str) -> str:
    """One canon line's worth of text, or refuse before touching disk.

    The delta schema checks this too. It is repeated here because
    vault.py is the trust boundary that matters: a caller that skipped
    validation must not be able to close a marker block from inside it.
    """
    text = value.strip()
    if not text:
        raise VaultError(f"{field} is empty; refusing to append a blank line.")
    if "\n" in text or "\r" in text:
        raise VaultError(f"{field} spans multiple lines; a canon entry is one line.")
    if "<!--" in text or "-->" in text:
        raise VaultError(
            f"{field} contains HTML comment syntax; it would break the marker "
            "block it is appended inside."
        )
    return text


def _split_block(
    path: Path, begin: str, end: str, text: str | None = None
) -> tuple[str, str, str]:
    """(before, inside, after) for exactly one marker block."""
    if text is None:
        text = path.read_text(encoding="utf-8")
    if text.count(begin) != 1 or text.count(end) != 1:
        raise VaultError(
            f"{path} must contain exactly one {begin} and one {end}; found "
            f"{text.count(begin)} and {text.count(end)}."
        )
    pre, rest = text.split(begin, 1)
    section, post = rest.split(end, 1)
    if not section.endswith("\n"):
        raise VaultError(f"{path}: {end} is not at the start of its own line.")
    return pre, section, post


def _append_in_block(path: Path, begin: str, end: str, line: str) -> str:
    """Insert `line` immediately before `end`. Returns the new file text.

    Byte-surgical in the shape of flip_manifest_status (decision #16):
    every other byte of the file is preserved verbatim, and the write is
    verified to have added exactly that one line and changed nothing
    else.
    """
    pre, section, post = _split_block(path, begin, end)
    before = pre + begin + section + end + post
    if line in section.splitlines():
        raise VaultError(
            f"{path} already contains this exact line; refusing to append a "
            f"duplicate:\n  {line}"
        )
    after = pre + begin + section + line + "\n" + end + post
    path.write_text(after, encoding="utf-8")

    on_disk = path.read_text(encoding="utf-8")
    if on_disk != after:
        raise VaultError(f"{path}: what landed on disk is not what was written.")
    old_lines = before.splitlines()
    new_lines = on_disk.splitlines()
    index = len((pre + begin + section).splitlines())
    if new_lines != [*old_lines[:index], line, *old_lines[index:]]:
        raise VaultError(
            f"{path}: the append changed more than one line. Restore the file "
            "from git before re-running."
        )
    return on_disk


def append_fact(
    book_root: Path,
    category: str,
    entity: str,
    chapter_number: int,
    text: str,
) -> str:
    """Append one locked fact to canon/continuity-tracker.md.

    Always tagged `[model]`. There is no origin parameter: the engine
    only ever appends facts a model proposed, and a code path able to
    write `[author]` would make model-invented canon indistinguishable
    from the author's within a few sessions (pitfall A4). Author facts
    are hand-written.

    Returns the line as stored.
    """
    text = _guard_line_text(text, "fact")
    scoped = f"{category}:{entity}" if entity else category
    line = f"- `[{scoped}]` `[ch-{chapter_number:03d}]` `[model]` {text}"

    path = book_root / "canon" / "continuity-tracker.md"
    # Parse BEFORE writing: appending to an already-malformed ledger
    # would bury the real problem under a successful-looking session.
    before = parse_facts(path.read_text(encoding="utf-8"), path)
    on_disk = _append_in_block(path, FACTS_BEGIN, FACTS_END, line)

    after = parse_facts(on_disk, path)
    if len(after) != len(before) + 1 or after[-1].raw != line:
        raise VaultError(
            f"{path}: the appended fact does not read back as one new fact "
            "line. Restore the file from git before re-running."
        )
    return line


def append_thread(book_root: Path, chapter_number: int, text: str) -> str:
    """Open a new thread in canon/open-threads.md. Returns its ID.

    IDs are allocated here, never by a model: the next ID is one above
    the highest currently in the file. Because the engine only ever
    appends and only ever flips status, that is enough for IDs never to
    repeat under engine operation — a resolved thread keeps its line and
    keeps its number.

    The one way a number can be reissued is an author DELETING a thread
    line by hand, which the engine cannot see. That is the author's
    action on an append-only file, not an engine guarantee.
    """
    text = _guard_line_text(text, "thread")
    path = book_root / "canon" / "open-threads.md"
    threads = _parse_threads(path)
    numbers = [int(match.group("thread_id").removeprefix("T-")) for match in threads]
    thread_id = f"T-{max(numbers, default=0) + 1:03d}"
    line = f"- `[{thread_id}]` `[open]` `[ch-{chapter_number:03d}]` {text}"

    on_disk = _append_in_block(path, THREADS_BEGIN, THREADS_END, line)
    after = _parse_threads(path, on_disk)
    if len(after) != len(threads) + 1 or after[-1].group("thread_id") != thread_id:
        raise VaultError(
            f"{path}: the appended thread does not read back. Restore the file "
            "from git before re-running."
        )
    return thread_id


def _parse_threads(path: Path, text: str | None = None) -> list[re.Match[str]]:
    """Every thread line in the block, or refuse on the first malformed one."""
    _, section, _ = _split_block(path, THREADS_BEGIN, THREADS_END, text)
    matches: list[re.Match[str]] = []
    for line in section.splitlines():
        if not line.strip():
            continue
        match = THREAD_LINE.match(line)
        if not match:
            raise VaultError(
                f"{path}: line does not match the thread grammar "
                "`[T-NNN]` `[open|resolved:ch-NNN]` `[ch-NNN]` <thread>:\n"
                f"  {line.strip()!r}"
            )
        matches.append(match)
    return matches


def flip_thread_status(
    book_root: Path,
    thread_id: str,
    resolved_in_chapter: int,
) -> None:
    """Mark one open thread resolved. The thread text is never rewritten.

    The second permitted mechanical edit in the project, and the same
    shape as the first (decision #16): one cell of one line changes,
    every other byte is preserved, and the result is verified before the
    call returns.
    """
    path = book_root / "canon" / "open-threads.md"
    text = path.read_text(encoding="utf-8")
    matches = _parse_threads(path, text)

    hits = [m for m in matches if m.group("thread_id") == thread_id]
    if not hits:
        raise VaultError(f"{path}: no thread {thread_id}.")
    if len(hits) > 1:
        raise VaultError(f"{path}: {thread_id} appears twice; refusing to guess.")
    match = hits[0]
    if match.group("status") != "open":
        raise VaultError(
            f"{path}: {thread_id} is already {match.group('status')!r}; "
            "a thread is resolved once."
        )

    old_line = match.group(0)
    new_line = old_line.replace(
        "`[open]`", f"`[resolved:ch-{resolved_in_chapter:03d}]`", 1
    )
    if text.count(old_line) != 1:
        raise VaultError(
            f"{path}: the line for {thread_id} is not unique in the file; "
            "refusing to splice."
        )
    new_text = text.replace(old_line, new_line, 1)
    path.write_text(new_text, encoding="utf-8")

    on_disk = path.read_text(encoding="utf-8")
    differing = [
        (old, new)
        for old, new in zip(text.splitlines(), on_disk.splitlines(), strict=True)
        if old != new
    ]
    flipped = _parse_threads(path, on_disk)
    changed = next(m for m in flipped if m.group("thread_id") == thread_id)
    if (
        len(differing) != 1
        or changed.group("status") != f"resolved:ch-{resolved_in_chapter:03d}"
        or changed.group("text") != match.group("text")
        or changed.group("chapter") != match.group("chapter")
    ):
        raise VaultError(
            f"{path}: the flip changed more than {thread_id}'s status. Restore "
            "the file from git before re-running."
        )


def append_deepen_question(book_root: Path, chapter_number: int, question: str) -> str:
    """Append one open question to canon/deepen-queue.md. Returns the line.

    The queue is for the author to answer later; the engine never flips
    a question to `answered:` — that date is the author's word, not a
    model's inference.
    """
    question = _guard_line_text(question, "deepen question")
    path = book_root / "canon" / "deepen-queue.md"
    line = f"- `[open]` `[ch-{chapter_number:03d}]` {question}"

    _, section, _ = _split_block(path, QUEUE_BEGIN, QUEUE_END)
    for existing in section.splitlines():
        if existing.strip() and not QUEUE_LINE.match(existing):
            raise VaultError(
                f"{path}: line does not match the queue grammar "
                "`[open|answered:YYYY-MM-DD]` `[ch-NNN]` <question>:\n"
                f"  {existing.strip()!r}"
            )
    on_disk = _append_in_block(path, QUEUE_BEGIN, QUEUE_END, line)
    if line not in on_disk.split(QUEUE_BEGIN, 1)[1].split(QUEUE_END, 1)[0].splitlines():
        raise VaultError(f"{path}: the appended question does not read back.")
    return line


def append_summary(book_root: Path, chapter_number: int, paragraph: str) -> None:
    """Append one `## ch-NNN` summary to log/chapter-summary.md.

    Not a marker block: the file is a chronological ledger sliced by
    heading (specs.md §7), so the append goes at the end and must stay
    in chapter order. A summary for a chapter that already has one is
    refused rather than duplicated — the context builder slices the last
    N headings and would otherwise show the same chapter twice.
    """
    body = paragraph.strip()
    if not body:
        raise VaultError("Chapter summary is empty; refusing to append it.")
    if any(line.startswith("## ") for line in body.splitlines()):
        raise VaultError(
            "Chapter summary contains a '## ' line, which would forge a "
            "second heading in the ledger."
        )

    path = book_root / "log" / "chapter-summary.md"
    text = path.read_text(encoding="utf-8")
    existing = recent_summaries(text, -1, path)
    chapters = [entry.chapter for entry in existing]
    if chapter_number in chapters:
        raise VaultError(
            f"{path}: ch-{chapter_number:03d} already has a summary; the "
            "ledger holds one paragraph per chapter."
        )
    if chapters and chapter_number < max(chapters):
        raise VaultError(
            f"{path}: refusing to append ch-{chapter_number:03d} after "
            f"ch-{max(chapters):03d}; the ledger is in chapter order."
        )

    heading = f"## ch-{chapter_number:03d}"
    new_text = text.rstrip("\n") + f"\n\n{heading}\n{body}\n"
    path.write_text(new_text, encoding="utf-8")

    on_disk = path.read_text(encoding="utf-8")
    after = recent_summaries(on_disk, -1, path)
    if (
        on_disk != new_text
        or len(after) != len(existing) + 1
        or after[-1].chapter != chapter_number
        or after[-1].paragraph != body
        or not on_disk.startswith(text.rstrip("\n"))
    ):
        raise VaultError(
            f"{path}: the appended summary does not read back as one new "
            "entry. Restore the file from git before re-running."
        )


# --- all-or-nothing application ---------------------------------------------


@contextmanager
def canon_transaction(paths: Sequence[Path]) -> Iterator[Path]:
    """Snapshot `paths`; restore every one of them if the block raises.

    Invariant 2 in the one place it is hard: applying a delta means
    several appends across several files, and a failure at the third one
    would otherwise leave canon in a state matching no session and no
    chapter (pitfall A2). The append primitives verify each write, so
    this exists for what they cannot catch — a later step failing after
    an earlier one already landed.

    The only bytes this can ever write are bytes it read from the same
    file moments earlier: there is no path here for model text to reach
    a canon body. On failure the snapshot directory is KEPT and named in
    the raised error, so a restore that itself failed is diagnosable.

    Not a substitute for OQ-01: this recovers one interrupted apply, not
    a session an author wants to undo tomorrow.
    """
    scratch = Path(tempfile.mkdtemp(prefix="novel-engine-canon-"))
    saved: dict[Path, Path] = {}
    for path in paths:
        if not path.is_file():
            raise VaultError(f"Cannot snapshot {path}: it does not exist.")
        copy = scratch / f"{len(saved):02d}-{path.name}"
        shutil.copy2(path, copy)
        saved[path] = copy

    try:
        yield scratch
    except BaseException as exc:
        failures: list[str] = []
        for path, copy in saved.items():
            try:
                shutil.copy2(copy, path)
            except OSError as restore_error:  # pragma: no cover - disk failure
                failures.append(f"{path}: {restore_error}")
        detail = (
            f" RESTORE FAILED for {'; '.join(failures)}." if failures else " Restored."
        )
        raise VaultError(
            f"Canon change aborted: {exc}.{detail} Pre-change copies are in {scratch}."
        ) from exc
    shutil.rmtree(scratch, ignore_errors=True)


# --- session pointer --------------------------------------------------------


def next_step_path(book_root: Path) -> Path:
    return book_root / "log" / "next-step.md"


def read_next_step(book_root: Path) -> NextStep:
    path = next_step_path(book_root)
    if not path.is_file():
        raise VaultError(f"Missing next-step pointer: {path}.")
    return parse_next_step(path.read_text(encoding="utf-8"))


def write_next_step(book_root: Path, step: NextStep) -> Path:
    """Write log/next-step.md. The only canon-adjacent overwrite primitive (specs §8).

    - Mode is overwrite (architecture §3: pure operational pointer, no history value).
    - Writes the frontmatter machine contract and the prose note.
    - Re-reads from disk and verifies that what landed parses back to an
      identical NextStep.
    """
    path = next_step_path(book_root)
    if not path.parent.is_dir():
        raise VaultError(f"Missing log directory: {path.parent}.")

    text = serialize_next_step(step)
    path.write_text(text, encoding="utf-8")

    verified = parse_next_step(path.read_text(encoding="utf-8"))
    if verified != step:
        raise VaultError(
            f"Post-write verification failed for {path}: content on disk "
            "does not match the NextStep object."
        )
    return path
