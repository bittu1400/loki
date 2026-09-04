"""Deterministic entity check (decision #39, ADR-0012).

The two tests that matter are the two measurements the module was tuned
against: ZERO findings on every committed fixture chapter, and a finding
on the identity contradiction that the live editor missed twice.
"""

from pathlib import Path

import pytest

from novel_engine.core.config import load_book_config
from novel_engine.core.context_builder import parse_facts, select_facts
from novel_engine.core.outline import resolve_target
from novel_engine.core.vault import split_chapter_file
from novel_engine.quality.continuity_entities import (
    find_entity_conflicts,
    name_tokens,
    render_entity_conflicts,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
FAKE_ENV = {
    key: f"test-{key}"
    for key in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
    )
}

#: The sentence pair planted for the OQ-10 experiment on 2026-09-04. The
#: fact's wording ("echo ledger", "kept") is in the first sentence and
#: the wrong name in the second, which is why the check reads paragraphs.
PLANTED = (
    "The echo ledger itself had never been his. Brannec Tull had kept it "
    "since before Ovist's clerkship, and Ovist had never once been trusted "
    "to write in it."
)


@pytest.fixture
def book():
    return load_book_config(FIXTURE.parent, "example-book", env=FAKE_ENV)


def facts_for(book, chapter: int):
    tracker = (book.root / "canon" / "continuity-tracker.md").read_text(
        encoding="utf-8"
    )
    entry = resolve_target(book.manifest, chapter)
    return select_facts(
        parse_facts(tracker, book.root / "canon" / "continuity-tracker.md"),
        pov_id=entry.pov,
        beat_text=entry.beat,
        known_character_ids=list(book.characters),
        limit=book.pipeline.context.max_locked_facts,
    )


def body_of(book, chapter: int) -> str:
    path = book.root / "chapters" / f"chapter-{chapter:03d}.md"
    return split_chapter_file(path.read_text(encoding="utf-8"))[1]


def test_every_committed_chapter_is_clean(book) -> None:
    """The false-positive floor. ch-002 is the reason the proximity guard
    exists: it restates Brannec's own locked fact in a paragraph that also
    names Sela Vosk, and presence-based matching reported it."""
    for path in sorted((book.root / "chapters").glob("chapter-*.md")):
        number = int(path.stem.removeprefix("chapter-"))
        conflicts = find_entity_conflicts(
            facts_for(book, number), body_of(book, number), list(book.characters)
        )
        assert conflicts == [], f"false positive on ch-{number:03d}: {conflicts}"


def test_planted_identity_contradiction_is_found(book) -> None:
    body = body_of(book, 5).replace(
        "Ovist had written the corrections", PLANTED + "\n\nOvist had written"
    )
    conflicts = find_entity_conflicts(facts_for(book, 5), body, list(book.characters))

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.fact_character == "ovist-rhoam"
    assert conflict.chapter_character == "brannec-tull"
    assert "echo ledger" in conflict.fact_text
    assert "Brannec Tull had kept it" in conflict.chapter_sentence


def test_finding_is_rendered_as_prompt_evidence(book) -> None:
    body = body_of(book, 5).replace(
        "Ovist had written the corrections", PLANTED + "\n\nOvist had written"
    )
    rendered = render_entity_conflicts(
        find_entity_conflicts(facts_for(book, 5), body, list(book.characters))
    )
    assert "canon attributes this to ovist-rhoam" in rendered
    assert "the chapter names brannec-tull" in rendered


def test_empty_result_says_what_it_did_not_check() -> None:
    """OQ-10 in one line: an empty result must never read as a clean bill."""
    rendered = render_entity_conflicts([])
    assert "not a continuity review" in rendered
    assert "only sees names it can match" in rendered


def test_paragraph_naming_only_the_fact_subject_is_never_a_conflict(book) -> None:
    body = "Ovist Rhoam had kept the echo ledger since his clerkship began.\n"
    assert find_entity_conflicts(facts_for(book, 5), body, list(book.characters)) == []


def test_shared_wording_floor_rejects_a_bare_name_collision(book) -> None:
    """Two characters in one paragraph is not a contradiction."""
    body = "Brannec Tull came up the stairs and did not look at Ovist.\n"
    assert find_entity_conflicts(facts_for(book, 5), body, list(book.characters)) == []


def test_name_tokens_splits_kebab_ids_and_drops_short_parts() -> None:
    assert name_tokens("ovist-rhoam") == {"ovist", "rhoam"}
    assert name_tokens("sela-vosk") == {"sela", "vosk"}
    assert name_tokens("li-wu") == set()  # both parts too short to match on
