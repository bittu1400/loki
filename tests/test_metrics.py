"""Deterministic metric tests: hand-computed values on small fixtures,
plus a real run over the committed chapters in vault/example-book/."""

from pathlib import Path

import pytest

from novel_engine.core.context_builder import banned_phrases
from novel_engine.core.vault import split_chapter_file
from novel_engine.quality.metrics import (
    adverb_rate,
    banned_phrase_hits,
    banned_phrase_pattern,
    compute_metrics,
    dialogue_ratio,
    prose_paragraphs,
    repeated_openings,
    sentences,
    type_token_ratio,
    word_count,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"

SAMPLE = """# Chapter 9 — Salt

He counted the glass. He logged it slowly. The tide came in.

"You are late," she said. "Again."

Ovist wrote the hour down — nine, then nine again; the lamp guttered.
"""


def test_headings_are_not_paragraphs():
    paragraphs = prose_paragraphs(SAMPLE)
    assert len(paragraphs) == 3
    assert not any(p.startswith("#") for p in paragraphs)


def test_wrapped_lines_join_into_one_paragraph():
    assert prose_paragraphs("One line\nsecond line.\n\nNext.") == [
        "One line second line.",
        "Next.",
    ]


def test_sentence_split_strips_terminators_and_quotes():
    assert sentences('He ran. "Stop," she said. Then nothing!') == [
        "He ran",
        '"Stop," she said',
        "Then nothing",
    ]


def test_word_count_matches_split_convention():
    assert word_count("one two  three\nfour") == 4


def test_adverb_rate_excludes_non_adverb_ly_words():
    # "slowly" and "quietly" count; "only", "family", "reply" do not.
    prose = "He only replied slowly to his family and quietly filed the reply."
    assert adverb_rate(prose, total_words=100) == pytest.approx(20.0)


def test_type_token_ratio_counts_unique_lowercased_words():
    assert type_token_ratio("Salt salt glass tide") == pytest.approx(3 / 4)


def test_dialogue_ratio_counts_quoted_words_only():
    prose = '"You are late," she said.'
    # 3 quoted tokens ("You are late,") out of 5 total.
    assert dialogue_ratio(prose, total_words=5) == pytest.approx(3 / 5)


def test_unclosed_quote_contributes_no_dialogue():
    assert dialogue_ratio('"You are late, she said.', total_words=5) == 0.0


def test_repeated_openings_ranks_by_count():
    found = repeated_openings(["He ran", "He stopped", "She waited", "he sat"])
    assert found == {"he": 3}


def test_banned_phrase_pattern_uses_the_quoted_fragment():
    assert banned_phrase_pattern('"dance" as a verb for non-dancers') == "dance"
    assert banned_phrase_pattern("a testament to") == "a testament to"


def test_banned_phrase_hits_are_whole_word_and_case_insensitive():
    prose = "A Testament To nothing. The palpable dark. Palpables are fine."
    hits = banned_phrase_hits(prose, ["a testament to", "palpable"])
    assert hits == {"a testament to": 1, "palpable": 1}


def test_sample_metrics_are_hand_computable():
    metrics = compute_metrics(SAMPLE, banned=["palpable"], target_words=100)

    assert metrics.paragraph_count == 3
    assert metrics.paragraph_lengths == [12, 6, 13]
    assert metrics.word_count == 31
    assert metrics.words_vs_target == pytest.approx(0.31)

    # 3 + 2 + 1 sentences across the three paragraphs.
    assert metrics.sentence_count == 6
    assert metrics.sentence_length_mean == pytest.approx(31 / 6)

    assert metrics.em_dash_rate_per_1000 == pytest.approx(1000 / 31)
    assert metrics.semicolon_rate_per_1000 == pytest.approx(1000 / 31)
    assert metrics.adverb_rate_per_1000 == pytest.approx(1000 / 31)  # "slowly"
    assert metrics.repeated_openings == {"he": 2}
    assert metrics.banned_phrase_hits == {}


def test_empty_body_yields_zeroes_not_errors():
    metrics = compute_metrics("", banned=["palpable"])
    assert metrics.word_count == 0
    assert metrics.sentence_count == 0
    assert metrics.paragraph_length_max == 0
    assert metrics.type_token_ratio == 0.0
    assert metrics.words_vs_target is None


def test_single_sentence_has_zero_stdev():
    assert compute_metrics("Just the one.").sentence_length_stdev == 0.0


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_committed_chapters_measure_without_api_or_error(number):
    chapter = FIXTURE / "chapters" / f"chapter-{number:03d}.md"
    fields, body = split_chapter_file(chapter.read_text(encoding="utf-8"))
    style_guide = (FIXTURE / "canon" / "style-guide.md").read_text(encoding="utf-8")
    banned = banned_phrases(style_guide)

    metrics = compute_metrics(body, banned=banned, target_words=fields["target_words"])

    # Body word count tracks the frontmatter's actual_words; the metric
    # drops the chapter heading and any scene-break markers, so it is
    # slightly lighter and never heavier.
    dropped = fields["actual_words"] - metrics.word_count
    assert 0 <= dropped <= 0.01 * fields["actual_words"] + 5
    assert metrics.sentence_count > 0
    assert 0.0 < metrics.type_token_ratio <= 1.0
    assert 0.0 <= metrics.dialogue_ratio <= 1.0
    assert metrics.paragraph_length_max >= metrics.paragraph_length_mean
