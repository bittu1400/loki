"""The deterministic number check (decision #30).

Its whole reason for existing is one measured failure: a live editor
model, with the locked fact six lines above the chapter text, reported
no violation when the chapter said nine and canon said two. These tests
pin the catch and — just as important — the false positives that the
same live run produced and this check must not repeat."""

from pathlib import Path

import pytest

from novel_engine.core.context_builder import parse_facts
from novel_engine.core.vault import split_chapter_file
from novel_engine.quality.continuity_numbers import (
    find_number_conflicts,
    quantities,
    render_conflicts,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
FACTS = parse_facts((FIXTURE / "canon" / "continuity-tracker.md").read_text())

# The sentence from the pre-fix ch-005 (git d518b74) that no model caught.
CONTRADICTION = (
    "Nine corrections on the spring-tide page, nine countersignings that "
    "pointed, by their margin numbers, to a clerk dead six years.\n"
)
# The false positive a live editor model reported on the same chapter.
FALSE_POSITIVE = (
    "Twelve years of them, bound in oilcloth and shelved by the clerk whose "
    "hand had countersigned the original entry, any echo that might later be "
    "disputed.\n"
)
# A sentence that states the canonical number AND counts something else.
AGREES_AND_COUNTS = (
    "Eleven years of his tenure, then one year of his predecessor, Ferain "
    "Hoss, who had kept the cabinet under lock.\n"
)


def test_quantities_reads_words_and_digits() -> None:
    assert quantities("nine corrections and 2 pages") == [
        ("correction", 9),
        ("page", 2),
    ]
    assert quantities("Eleven years later") == [("year", 11)]
    assert quantities("two hundred") == []  # the noun is another number


def test_the_contradiction_no_model_caught_is_found() -> None:
    conflicts = find_number_conflicts(FACTS, CONTRADICTION)

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert (conflict.noun, conflict.fact_value, conflict.chapter_value) == (
        "correction",
        2,
        9,
    )
    assert "two corrections" in conflict.fact_text
    assert "Nine corrections" in conflict.chapter_sentence
    assert "canon says 2, the chapter says 9" in conflict.describe()


def test_a_shared_noun_alone_is_not_a_conflict() -> None:
    """'kept the ledger eleven years' vs 'twelve years of them, bound in
    oilcloth' share one incidental word. A live model called this a
    critical violation; this check must not."""
    assert find_number_conflicts(FACTS, FALSE_POSITIVE) == []


def test_a_sentence_that_also_states_the_canonical_number_is_consistent() -> None:
    assert find_number_conflicts(FACTS, AGREES_AND_COUNTS) == []


def test_every_committed_chapter_is_clean() -> None:
    """Regression net: the fixture's chapters, including the hand-fixed
    ch-005, must produce no findings at all."""
    for path in sorted((FIXTURE / "chapters").glob("chapter-*.md")):
        _, body = split_chapter_file(path.read_text(encoding="utf-8"))
        assert find_number_conflicts(FACTS, body) == [], path.name


def test_no_facts_with_numbers_means_no_work() -> None:
    unnumbered = [fact for fact in FACTS if not quantities(fact.text)]
    assert find_number_conflicts(unnumbered, CONTRADICTION) == []


def test_render_says_so_explicitly_when_nothing_disagreed() -> None:
    rendered = render_conflicts([])
    assert "no quantity" in rendered
    assert "not a continuity review" in rendered


def test_render_lists_each_finding() -> None:
    rendered = render_conflicts(find_number_conflicts(FACTS, CONTRADICTION))
    assert rendered.startswith("- ")
    assert "canon says 2" in rendered
    assert "fact:" in rendered and "chapter:" in rendered


@pytest.mark.parametrize(
    "text",
    ["", "No numbers here at all.", "# Chapter 5 — A Heading\n"],
)
def test_bodies_with_nothing_to_compare(text) -> None:
    assert find_number_conflicts(FACTS, text) == []
