"""Context builder tests: fact parsing/retrieval, verbatim tail,
summary slicing, banned-phrase extraction, and full template assembly
against vault/example-book/."""

import shutil
from pathlib import Path

import pytest

from novel_engine.core.config import load_book_config
from novel_engine.core.context_builder import (
    SLOT_PATTERN,
    FactLine,
    banned_phrases,
    build_prompt,
    parse_facts,
    previous_chapter_tail,
    recent_summaries,
    select_facts,
)
from novel_engine.core.errors import ContextError

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
FAKE_ENV = {
    key: f"test-{key}"
    for key in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
        "AIHUBMIX_API_KEY",
        "COHERE_API_KEY",
        "GLM_API_KEY",
    )
}


@pytest.fixture
def book(tmp_path: Path):
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    return load_book_config(copied.parent, "example-book", env=FAKE_ENV)


def facts_from_lines(*lines: str) -> list[FactLine]:
    text = "<!-- FACTS:BEGIN -->\n" + "\n".join(lines) + "\n<!-- FACTS:END -->"
    return parse_facts(text)


# --- parse_facts -----------------------------------------------------------


def test_parse_facts_fixture_happy_path() -> None:
    text = (FIXTURE / "canon/continuity-tracker.md").read_text()
    facts = parse_facts(text)
    assert len(facts) == 8
    assert facts[0].category == "world"
    assert facts[0].entity is None
    assert facts[0].origin == "author"
    assert facts[2].category == "character:ovist-rhoam"
    assert facts[2].entity == "ovist-rhoam"


def test_parse_facts_rejects_malformed_line() -> None:
    text = (
        "<!-- FACTS:BEGIN -->\n"
        "- `[world]` `[ch-001]` `[author]` Fine line.\n"
        "- Kaelen cannot channel through iron.\n"
        "<!-- FACTS:END -->"
    )
    with pytest.raises(ContextError, match="fact grammar"):
        parse_facts(text)


def test_parse_facts_rejects_unknown_category() -> None:
    with pytest.raises(ContextError, match="unknown fact category"):
        facts_from_lines("- `[vibes]` `[ch-001]` `[author]` Bad category.")


def test_parse_facts_missing_markers() -> None:
    with pytest.raises(ContextError, match="exactly one"):
        parse_facts("- `[world]` `[ch-001]` `[author]` Orphan.")


# --- select_facts ----------------------------------------------------------


ALL_IDS = ["ovist-rhoam", "brannec-tull", "sela-vosk"]


def test_select_facts_pov_scoped_and_touching() -> None:
    facts = facts_from_lines(
        "- `[character:ovist-rhoam]` `[ch-001]` `[author]` Ovist keeps the ledger.",
        "- `[object]` `[ch-001]` `[author]` Corrections in Ovist's own hand.",
        "- `[character:sela-vosk]` `[ch-002]` `[model]` Sela Vosk pays triple.",
        "- `[world]` `[ch-001]` `[author]` Driftglass forms where tide meets stone.",
    )
    beat = "Ovist pulls nine years of gaps."
    selected = select_facts(facts, "ovist-rhoam", beat, ALL_IDS, 40)
    # POV-scoped + the object fact naming Ovist; Sela and pure-world excluded.
    assert [f.entity or f.category for f in selected] == [
        "ovist-rhoam",
        "object",
    ]


def test_select_facts_beat_named_character_included() -> None:
    facts = facts_from_lines(
        "- `[character:sela-vosk]` `[ch-002]` `[model]` Sela Vosk pays triple.",
    )
    beat = "Sela Vosk names her price."
    selected = select_facts(facts, "brannec-tull", beat, ALL_IDS, 40)
    assert len(selected) == 1 and selected[0].entity == "sela-vosk"


def test_select_facts_cap_respected_scoped_first() -> None:
    facts = facts_from_lines(
        "- `[location]` `[ch-001]` `[author]` Somewhere Ovist walks daily.",
        "- `[character:ovist-rhoam]` `[ch-001]` `[author]` Ovist keeps the ledger.",
    )
    selected = select_facts(facts, "ovist-rhoam", "A quiet audit.", ALL_IDS, 1)
    assert len(selected) == 1
    assert selected[0].entity == "ovist-rhoam"


def test_select_facts_no_match_returns_empty() -> None:
    facts = facts_from_lines(
        "- `[world]` `[ch-001]` `[author]` The tide crosses old stone.",
    )
    assert select_facts(facts, "brannec-tull", "An empty beat.", ALL_IDS, 40) == []


# --- previous_chapter_tail -------------------------------------------------


def test_previous_tail_is_verbatim_slice(book) -> None:
    source, tail = previous_chapter_tail(book.root / "chapters", 3, 10)
    body = (book.root / "chapters/chapter-002.md").read_text()
    assert source == 2
    assert tail.split() == body.split()[-10:]


def test_previous_tail_preserves_internal_whitespace(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    body = "First words here.\n\nThe  ending   keeps\nits   spacing exactly."
    (chapters / "chapter-001.md").write_text(body)
    source, tail = previous_chapter_tail(chapters, 2, 5)
    assert source == 1
    assert tail == "ending   keeps\nits   spacing exactly."


def test_previous_tail_skips_frontmatter(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    (chapters / "chapter-001.md").write_text(
        "---\nchapter_number: 1\n---\n\nProse after frontmatter."
    )
    _, tail = previous_chapter_tail(chapters, 2, 2)
    assert tail == "after frontmatter."


def test_previous_tail_no_prior_chapter(tmp_path: Path) -> None:
    source, tail = previous_chapter_tail(tmp_path, 1, 500)
    assert source is None
    assert "opening" in tail


def test_previous_tail_ignores_chapter_at_or_above_target(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    (chapters / "chapter-004.md").write_text("Later chapter.")
    source, _ = previous_chapter_tail(chapters, 3, 10)
    assert source is None


# --- recent_summaries ------------------------------------------------------


def test_recent_summaries_takes_last_n_in_order() -> None:
    text = (FIXTURE / "log/chapter-summary.md").read_text()
    entries = recent_summaries(text, 1)
    assert [e.chapter for e in entries] == [2]
    assert "Brannec Tull" in entries[0].paragraph
    both = recent_summaries(text, 5)
    assert [e.chapter for e in both] == [1, 2]


def test_recent_summaries_empty_file() -> None:
    assert recent_summaries("# nothing here", 2) == []


# --- banned_phrases --------------------------------------------------------


def test_banned_phrases_from_fixture_style_guide() -> None:
    text = (FIXTURE / "canon/style-guide.md").read_text()
    phrases = banned_phrases(text)
    assert "a testament to" in phrases
    assert "palpable" in phrases


def test_banned_phrases_missing_section_raises() -> None:
    with pytest.raises(ContextError, match="Banned phrases"):
        banned_phrases("# Style Guide\n\nNo list here.")


# --- build_prompt ----------------------------------------------------------


def test_build_prompt_fills_all_slots_against_fixture(book) -> None:
    assembled = build_prompt(book, 3)
    # No *unfilled* slots remain (the template's own header comment may
    # legitimately contain the literal characters {{ }}).
    assert SLOT_PATTERN.search(assembled.text) is None
    assert "{{beat}}" not in assembled.text
    assert "Ovist pulls nine years of countersignature gaps" in assembled.text
    assert assembled.pov == "ovist-rhoam"
    assert assembled.tail_source_chapter == 2
    assert assembled.summary_chapters == [1, 2]
    # Stable→volatile slot order preserved from the template file.
    assert assembled.text.index("# Style Guide") < assembled.text.index(
        "# Previous Chapter"
    )


def test_build_prompt_locked_facts_are_retrieved_not_dumped(book) -> None:
    assembled = build_prompt(book, 3)
    raw_lines = [f.raw for f in assembled.locked_facts]
    assert any("echo ledger" in line for line in raw_lines)
    # Brannec/Sela-scoped facts are irrelevant to an Ovist-only beat.
    assert not any("pays triple" in line for line in raw_lines)


def test_build_prompt_slot_order_beats_beat_instructions_last(book) -> None:
    assembled = build_prompt(book, 3)
    instructions_pos = assembled.text.index("Write this chapter in full")
    assert instructions_pos > assembled.text.index("Beat:")
    assert "1000 words" in assembled.text


def test_build_prompt_unknown_chapter_number(book) -> None:
    with pytest.raises(ContextError, match="manifest"):
        build_prompt(book, 99)


def test_build_prompt_missing_character_sheet(book) -> None:
    (book.root / "characters/ovist-rhoam.md").unlink()
    with pytest.raises(ContextError, match="Cannot read"):
        build_prompt(book, 3)


TEMPLATE_SLOTS = (
    "style_guide",
    "story_bible",
    "character_sheet",
    "locked_facts",
    "banned_phrases",
    "recent_summaries",
    "previous_tail",
    "pov_character",
    "beat",
    "chapter_instructions",
)


@pytest.mark.parametrize("slot", TEMPLATE_SLOTS)
def test_unfilled_value_without_template_slot_errors(book, slot: str) -> None:
    template_path = book.root / "config/prompt-template.md"
    template = template_path.read_text()
    template_path.write_text(template.replace(f"{{{{{slot}}}}}\n", ""))
    with pytest.raises(ContextError, match=slot):
        build_prompt(book, 3)


def test_unknown_template_slot_errors(book) -> None:
    template_path = book.root / "config/prompt-template.md"
    template_path.write_text(
        template_path.read_text().replace("{{beat}}", "{{mystery_slot}}")
    )
    with pytest.raises(ContextError, match="mystery_slot"):
        build_prompt(book, 3)
