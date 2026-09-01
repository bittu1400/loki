"""Bounded context assembly, retrieval by entity, token budgeting.

Builds the drafting prompt by filling config/prompt-template.md slots IN
FILE ORDER (stable material first, volatile last — models weight recency,
so the instruction nearest generation is about THIS chapter).

Reading rules:
- Locked facts are RETRIEVED, not dumped: only facts whose category
  touches the POV or an entity named in the beat, capped at
  `context.max_locked_facts` (pitfall A3).
- The previous chapter's tail is injected VERBATIM (pitfall B2) — the
  seam between chapters is where continuity is perceived.
- Every parse failure raises ContextError before any API call. Reading
  canon fails loudly rather than prompting a model with wrong context.

This module returns data only; it never writes to disk (one-writer rule,
core/vault.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from novel_engine.core.config import BookConfig
from novel_engine.core.errors import ContextError

FACTS_BEGIN = "<!-- FACTS:BEGIN -->"
FACTS_END = "<!-- FACTS:END -->"

#: `- `[<category>]` `[ch-<NNN>]` `[<origin>]` <fact sentence>` (specs.md §4)
FACT_LINE = re.compile(
    r"^- `\[(?P<category>[a-z]+(?::[a-z0-9-]+)?)\]` "
    r"`\[ch-(?P<chapter>\d+)\]` "
    r"`\[(?P<origin>author|model)\]` "
    r"(?P<text>.+)$"
)
SCOPED_CATEGORY = re.compile(r"^character:(?P<id>[a-z0-9]+(-[a-z0-9]+)*)$")
UNSCOPED_CATEGORIES = {"world", "magic", "timeline", "object", "location"}

SUMMARY_HEADING = re.compile(r"^## ch-(\d+)\s*$", re.MULTILINE)
SLOT_PATTERN = re.compile(r"\{\{([a-z_]+)\}\}")
WORD_PATTERN = re.compile(r"\S+")


class FactLine(BaseModel):
    """One atomic locked fact, parsed from the continuity tracker."""

    category: str
    entity: str | None  # set only for character:<id> categories
    chapter: int
    origin: str  # author | model
    text: str
    raw: str  # the verbatim source line


def _extract_facts_section(text: str, path: Path) -> str:
    begin = text.count(FACTS_BEGIN)
    end = text.count(FACTS_END)
    if begin != 1 or end != 1:
        raise ContextError(
            f"{path} must contain exactly one {FACTS_BEGIN} and one "
            f"{FACTS_END} marker; found {begin} and {end}."
        )
    return text.split(FACTS_BEGIN, 1)[1].split(FACTS_END, 1)[0]


def parse_facts(tracker_text: str, path: Path | None = None) -> list[FactLine]:
    """Parse FACTS lines with the line grammar from the tracker header.

    Any line inside the markers that does not match the grammar is an
    error, not a skipped line — a fact that cannot be parsed cannot be
    retrieved, and silently dropping it corrupts canon by omission.
    """
    path = path or Path("canon/continuity-tracker.md")
    section = _extract_facts_section(tracker_text, path)
    facts: list[FactLine] = []
    for line in section.splitlines():
        if not line.strip():
            continue
        match = FACT_LINE.match(line)
        if not match:
            raise ContextError(
                f"{path}: line does not match the fact grammar "
                "`[<category>]` `[ch-<NNN>]` `[<origin>]` <sentence>:\n"
                f"  {line.strip()!r}"
            )
        category = match.group("category")
        scoped = SCOPED_CATEGORY.match(category)
        if not scoped and category not in UNSCOPED_CATEGORIES:
            legal = ", ".join(sorted(UNSCOPED_CATEGORIES)) + ", character:<id>"
            raise ContextError(
                f"{path}: unknown fact category {category!r}; "
                f"legal categories are: {legal}."
            )
        facts.append(
            FactLine(
                category=category,
                entity=scoped.group("id") if scoped else None,
                chapter=int(match.group("chapter")),
                origin=match.group("origin"),
                text=match.group("text"),
                raw=line,
            )
        )
    return facts


def _display_name(character_id: str) -> str:
    """'ovist-rhoam' -> 'ovist rhoam' — how prose refers to the id."""
    return character_id.replace("-", " ").lower()


def _name_tokens(character_id: str) -> list[str]:
    """Distinctive words of a name, long enough to match without noise."""
    return [token for token in _display_name(character_id).split() if len(token) >= 4]


def select_facts(
    facts: list[FactLine],
    pov_id: str,
    beat_text: str,
    known_character_ids: list[str],
    limit: int,
) -> list[FactLine]:
    """Facts touching the POV or entities named in the beat, capped.

    Selection rule (architecture.md §5):
    - every `character:<id>` fact where id is the POV or a character
      named in the beat;
    - plus unscoped facts (world/timeline/object/...) whose text mentions
      one of those characters by name token.

    Entity-scoped facts come first, then touching unscoped facts; file
    order preserved within each group. Deterministic. Capped at `limit`.
    """
    beat_lower = beat_text.lower()
    named = [
        cid
        for cid in known_character_ids
        if cid != pov_id and any(token in beat_lower for token in _name_tokens(cid))
    ]
    relevant_ids = {pov_id, *named}

    scoped = [f for f in facts if f.entity in relevant_ids]
    tokens = {t for cid in relevant_ids for t in _name_tokens(cid)}
    touching = [
        f
        for f in facts
        if f.entity is None and any(token in f.text.lower() for token in tokens)
    ]
    selected = scoped + touching
    return selected[:limit] if limit >= 0 else selected


def previous_chapter_tail(
    chapters_dir: Path,
    target_number: int,
    tail_words: int,
) -> tuple[int | None, str]:
    """(source chapter, final `tail_words` words VERBATIM) or (None, note).

    The highest existing chapter below the target supplies the tail. The
    slice preserves internal whitespace and punctuation exactly: word
    counting uses regex spans, never split(), so what the model sees at
    the seam is byte-for-byte the author's/generated ending.
    """
    numbers = []
    for entry in chapters_dir.glob("chapter-*.md"):
        digits = entry.stem.removeprefix("chapter-")
        if digits.isdigit():
            numbers.append(int(digits))
    prior = [n for n in numbers if n < target_number]
    if not prior:
        return None, "(No previous chapter — this is the opening of the book.)"

    source = max(prior)
    body = _read_chapter_body(chapters_dir / f"chapter-{source:03d}.md")
    matches = list(WORD_PATTERN.finditer(body))
    if len(matches) <= tail_words:
        return source, body.strip()
    start = matches[-tail_words].start()
    return source, body[start:].strip()


def _read_chapter_body(path: Path) -> str:
    """Chapter content after frontmatter, leading blank lines stripped."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[text.find("\n", end + 1) + 1 :]
    return text.lstrip("\n")


@dataclass
class SummaryEntry:
    chapter: int
    paragraph: str


def recent_summaries(
    summary_text: str, count: int, path: Path | None = None
) -> list[SummaryEntry]:
    """Last `count` entries from log/chapter-summary.md, in chapter order."""
    path = path or Path("log/chapter-summary.md")
    headings = list(SUMMARY_HEADING.finditer(summary_text))
    entries: list[SummaryEntry] = []
    for i, heading in enumerate(headings):
        start = heading.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(summary_text)
        paragraph = summary_text[start:end].strip()
        if paragraph:
            entries.append(
                SummaryEntry(chapter=int(heading.group(1)), paragraph=paragraph)
            )
    return entries[-count:] if count >= 0 else entries


def banned_phrases(style_guide_text: str, path: Path | None = None) -> list[str]:
    """Bullet items under the style guide's '## Banned phrases' section."""
    path = path or Path("canon/style-guide.md")
    lines = style_guide_text.splitlines()
    phrases: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip().lower() == "## banned phrases"
            continue
        if in_section and line.lstrip().startswith(("- ", "* ")):
            item = line.lstrip()[2:].strip().strip('"')
            if item:
                phrases.append(item)
    if not phrases:
        raise ContextError(
            f"{path}: no banned phrases found under a '## Banned phrases' "
            "heading. Add the list — it feeds both the prompt and the "
            "Phase 4 deterministic checks."
        )
    return phrases


@dataclass
class AssembledPrompt:
    """The filled template plus provenance about what went into it."""

    text: str
    chapter_number: int
    pov: str
    beat: str
    locked_facts: list[FactLine] = field(default_factory=list)
    tail_source_chapter: int | None = None
    summary_chapters: list[int] = field(default_factory=list)


def build_prompt(book: BookConfig, chapter_number: int) -> AssembledPrompt:
    """Assemble the full drafting prompt for one chapter. Reads only."""
    root = book.root
    entry = next(
        (e for e in book.manifest if e.chapter_number == chapter_number),
        None,
    )
    if entry is None:
        planned = ", ".join(str(e.chapter_number) for e in book.manifest)
        raise ContextError(
            f"Chapter {chapter_number} is not in the manifest of "
            f"{book.slug!r} (manifest chapters: {planned}). Chapter "
            "numbers come from the manifest, never from the filesystem."
        )

    pov = entry.pov
    character_entry = book.characters.get(pov)
    if character_entry is None:
        raise ContextError(
            f"Manifest POV {pov!r} has no entry in characters/index.yaml."
        )

    def read(relative: str) -> str:
        path = root / relative
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContextError(f"Cannot read {path}: {exc}") from exc

    style_guide_text = read("canon/style-guide.md")
    story_bible_text = read("canon/story-bible.md")
    tracker_text = read("canon/continuity-tracker.md")
    summaries_text = read("log/chapter-summary.md")
    template = read("config/prompt-template.md")
    character_sheet_text = read(f"characters/{character_entry.file}")

    facts = parse_facts(tracker_text, root / "canon/continuity-tracker.md")
    selected = select_facts(
        facts,
        pov_id=pov,
        beat_text=entry.beat,
        known_character_ids=list(book.characters),
        limit=book.pipeline.context.max_locked_facts,
    )

    tail_source, tail = previous_chapter_tail(
        root / "chapters",
        chapter_number,
        book.pipeline.context.previous_chapter_tail_words,
    )

    summaries = recent_summaries(
        summaries_text,
        book.pipeline.context.recent_summaries,
        root / "log/chapter-summary.md",
    )
    summaries_block = (
        "\n\n".join(
            f"## ch-{entry_summary.chapter:03d}\n{entry_summary.paragraph}"
            for entry_summary in summaries
        )
        or "(No chapter summaries recorded yet.)"
    )

    phrases = banned_phrases(style_guide_text, root / "canon/style-guide.md")
    banned_block = "\n".join(f"- {phrase}" for phrase in phrases)

    target = book.pipeline.target_words
    low = target - round(target * book.pipeline.word_tolerance)
    high = target + round(target * book.pipeline.word_tolerance)
    instructions = (
        f"Write this chapter in full, aiming for {target} words "
        f"(accept {low}\u2013{high}). Continue seamlessly from the "
        "previous chapter's closing words — do not summarise, restart, "
        "or resolve anything the summary material already covers. Stay "
        "in the POV's head; never head-hop. Never use a banned phrase."
    )

    slot_values: dict[str, str] = {
        "style_guide": style_guide_text.strip(),
        "story_bible": story_bible_text.strip(),
        "character_sheet": character_sheet_text.strip(),
        "locked_facts": (
            "\n".join(f.raw for f in selected) or "(No locked facts touch this scene.)"
        ),
        "banned_phrases": banned_block,
        "recent_summaries": summaries_block,
        "previous_tail": tail,
        "pov_character": pov,
        "beat": entry.beat,
        "chapter_instructions": instructions,
    }

    filled = fill_template(template, slot_values, root / "config/prompt-template.md")

    return AssembledPrompt(
        text=filled,
        chapter_number=chapter_number,
        pov=pov,
        beat=entry.beat,
        locked_facts=selected,
        tail_source_chapter=tail_source,
        summary_chapters=[s.chapter for s in summaries],
    )


def fill_template(template: str, values: dict[str, str], path: Path) -> str:
    """Substitute slots strictly in order of appearance in the template.

    Shared with the editorial prompt (decision #26), which is packaged
    rather than per-book but is filled by exactly the same rules: an
    unknown slot or a value with no slot is a hard error before any API
    call (decision #13).
    """
    out: list[str] = []
    cursor = 0
    seen: set[str] = set()
    for match in SLOT_PATTERN.finditer(template):
        slot = match.group(1)
        if slot not in values:
            raise ContextError(
                f"{path}: template slot {{{{{slot}}}}} has no value. "
                f"Known slots: {', '.join(sorted(values))}."
            )
        out.append(template[cursor : match.start()])
        out.append(values[slot])
        cursor = match.end()
        seen.add(slot)
    out.append(template[cursor:])
    unfilled = sorted(set(values) - seen)
    if unfilled:
        raise ContextError(
            f"{path}: value(s) with no slot in the template: "
            f"{', '.join(unfilled)}. Template and builder disagree."
        )
    return "".join(out)
