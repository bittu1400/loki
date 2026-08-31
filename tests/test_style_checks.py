"""Threshold parsing and verdicts: marker discipline, loud failure on a
malformed block, silence on an absent one, and a real report over the
committed chapters in vault/example-book/."""

from pathlib import Path

import pytest

from novel_engine.core.vault import split_chapter_file
from novel_engine.quality.metrics import compute_metrics
from novel_engine.quality.style_checks import (
    COMPARABLE_METRICS,
    StyleCheckError,
    Threshold,
    build_report,
    judge,
    parse_thresholds,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
STYLE_GUIDE = (FIXTURE / "canon" / "style-guide.md").read_text(encoding="utf-8")


def block(*rows: str) -> str:
    body = "\n".join(rows)
    return (
        "## Banned phrases\n\n- palpable\n\n"
        f"<!-- THRESHOLDS:BEGIN -->\n| metric | min | max |\n|---|---|---|\n{body}\n"
        "<!-- THRESHOLDS:END -->\n"
    )


def test_absent_block_is_silent_and_yields_no_verdicts():
    guide = "## Banned phrases\n\n- palpable\n\n## Rhythm\n\nMean near 14.\n"
    assert parse_thresholds(guide) == {}

    report = build_report("b", 1, "He ran. She waited.", guide)
    assert report.thresholds_present is False
    assert report.verdicts == []
    assert report.metrics.sentence_count == 2


def test_both_bounds_parse():
    thresholds = parse_thresholds(block("| dialogue_ratio | 0.05 | 0.45 |"))
    assert thresholds == {"dialogue_ratio": Threshold("dialogue_ratio", 0.05, 0.45)}


@pytest.mark.parametrize("dash", ["-", "\u2013", "\u2014", "", "none"])
def test_dashes_and_blanks_mean_unbounded(dash):
    thresholds = parse_thresholds(block(f"| adverb_rate_per_1000 | {dash} | 12 |"))
    assert thresholds["adverb_rate_per_1000"].minimum is None
    assert thresholds["adverb_rate_per_1000"].maximum == 12


def test_prose_outside_the_markers_is_not_parsed():
    guide = (
        "| sentence_length_mean | 1 | 2 |\n\n"
        + block("| dialogue_ratio | - | 0.45 |")
        + "\n| adverb_rate_per_1000 | - | 1 |\n"
    )
    assert set(parse_thresholds(guide)) == {"dialogue_ratio"}


@pytest.mark.parametrize(
    "row",
    [
        "| dialogue_ratio | 0.05 |",  # missing a cell
        "| dialogue_ratio | loose | 0.45 |",  # non-numeric bound
        "| dialog_ratio | - | 0.45 |",  # unknown metric
        "| dialogue_ratio | - | - |",  # bounds nothing
        "| dialogue_ratio | 0.9 | 0.1 |",  # inverted band
        "| banned_phrase_hits | - | 3 |",  # not a scalar metric
    ],
)
def test_malformed_rows_fail_loudly(row):
    with pytest.raises(StyleCheckError):
        parse_thresholds(block(row))


def test_duplicate_metric_rows_fail_loudly():
    with pytest.raises(StyleCheckError):
        parse_thresholds(
            block("| dialogue_ratio | - | 0.4 |", "| dialogue_ratio | - | 0.5 |")
        )


def test_unclosed_block_fails_loudly():
    with pytest.raises(StyleCheckError):
        parse_thresholds("<!-- THRESHOLDS:BEGIN -->\n| dialogue_ratio | - | 0.4 |\n")


def test_collection_metrics_are_never_bandable():
    assert "banned_phrase_hits" not in COMPARABLE_METRICS
    assert "repeated_openings" not in COMPARABLE_METRICS
    assert "paragraph_lengths" not in COMPARABLE_METRICS
    assert "target_words" not in COMPARABLE_METRICS
    assert "dialogue_ratio" in COMPARABLE_METRICS


def test_judge_labels_low_ok_and_high():
    metrics = compute_metrics("He ran. She waited longer than that.")
    thresholds = {
        "sentence_length_mean": Threshold("sentence_length_mean", 100, None),
        "adverb_rate_per_1000": Threshold("adverb_rate_per_1000", None, 1000),
        "semicolon_rate_per_1000": Threshold("semicolon_rate_per_1000", None, -1),
    }
    assert [(v.metric, v.status) for v in judge(metrics, thresholds)] == [
        ("sentence_length_mean", "low"),
        ("adverb_rate_per_1000", "ok"),
        ("semicolon_rate_per_1000", "high"),
    ]


def test_unset_metric_is_skipped_not_judged():
    metrics = compute_metrics("He ran.", target_words=None)
    thresholds = {"words_vs_target": Threshold("words_vs_target", 0.9, 1.6)}
    assert judge(metrics, thresholds) == []


def test_fixture_thresholds_flag_only_the_generated_chapters():
    flags = {}
    for number in (1, 2, 3, 4):
        chapter = FIXTURE / "chapters" / f"chapter-{number:03d}.md"
        fields, body = split_chapter_file(chapter.read_text(encoding="utf-8"))
        report = build_report(
            "example-book", number, body, STYLE_GUIDE, fields["target_words"]
        )
        assert report.thresholds_present is True
        flags[number] = {verdict.metric for verdict in report.flagged}

    # Hand-written canon sits inside its own book's bands; the two live
    # generated chapters drift exactly where the style guide warns.
    assert flags[1] == set()
    assert flags[2] == set()
    assert "sentence_length_mean" in flags[3]
    assert flags[4] == {"sentence_length_mean", "dialogue_ratio"}
