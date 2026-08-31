"""Deterministic prose metrics. Pure functions, no IO, no API (specs §14).

Every function here takes a chapter BODY (post-frontmatter prose) and
returns numbers. Nothing in this module reads a file, asks a model, or
decides whether a number is good — thresholds are the author's, and live
in each book's style-guide.md (decisions.md #22). Measuring is
engineering; judging is a creative choice.

Tokenisation notes, so hand-computed test values stay reproducible:
- `word_count` uses `text.split()`, the same convention as
  `drafting.generate.word_count`, so it matches `actual_words` in
  chapter frontmatter. It is deliberately not imported from there —
  the quality package must stay free of provider imports.
- Every rate is per 1000 words of that same count.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

#: Sentence terminator followed by whitespace or end-of-text.
# Abbreviations ("Mr. Tull") over-split here. Accepted: the metric is a
# rhythm signal, and a handful of extra boundaries per chapter moves the
# mean by well under a word. Revisit only if a real book trips on it.
CLOSERS = "[\"'”\u2019)\\]]*"  # \u2019 = curly apostrophe, written escaped
SENTENCE_SPLIT = re.compile(rf"(?<=[.!?…]){CLOSERS}\s+")
SENTENCE_TRAILING = re.compile(rf"{CLOSERS}[.!?…]+$")

#: A word for lexical metrics: letters plus internal apostrophes/hyphens.
LEXICAL_WORD = re.compile("[A-Za-z][A-Za-z'\u2019-]*")

#: Straight or curly double-quoted spans — dialogue, for the ratio.
DIALOGUE_SPAN = re.compile('"[^"]*"|“[^”]*”')

#: Markdown structure that is not prose and must not be counted.
NON_PROSE_LINE = re.compile(r"^\s*(#{1,6}\s|>\s|[-*+]\s|\d+\.\s|\|)")

#: A literal phrase quoted inside a style-guide bullet, e.g.
#: `"dance" as a verb for non-dancers` → `dance`.
QUOTED_FRAGMENT = re.compile('["“]([^"”]+)["”]')

#: `-ly` words that are not adverbs. Linguistic fact, not a threshold.
NON_ADVERB_LY = frozenset(
    {
        "ally",
        "apply",
        "belly",
        "bully",
        "comply",
        "family",
        "fly",
        "folly",
        "gully",
        "holy",
        "italy",
        "jelly",
        "jolly",
        "lily",
        "melancholy",
        "only",
        "ply",
        "rally",
        "rely",
        "reply",
        "silly",
        "sly",
        "supply",
        "tally",
        "ugly",
        "wholly",
    }
)


@dataclass(frozen=True)
class ChapterMetrics:
    """Every specs §14 metric for one chapter body. Advisory numbers only."""

    word_count: int
    target_words: int | None
    words_vs_target: float | None  # word_count / target_words

    sentence_count: int
    sentence_length_mean: float
    sentence_length_stdev: float

    adverb_rate_per_1000: float
    type_token_ratio: float
    dialogue_ratio: float

    em_dash_rate_per_1000: float
    semicolon_rate_per_1000: float

    paragraph_count: int
    paragraph_length_mean: float
    paragraph_length_max: int
    paragraph_lengths: list[int] = field(default_factory=list)

    banned_phrase_hits: dict[str, int] = field(default_factory=dict)
    repeated_openings: dict[str, int] = field(default_factory=dict)


def word_count(text: str) -> int:
    """Whitespace-run count — matches frontmatter `actual_words`."""
    return len(text.split())


def prose_paragraphs(body: str) -> list[str]:
    """Blank-line-separated paragraphs, minus headings, lists, and quotes.

    A chapter body opens with a `# Chapter N — Title` heading; counting it
    as a one-line paragraph would drag the paragraph-length mean down and
    make its first "sentence" the title.
    """
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        lines = [
            line
            for line in block.splitlines()
            if line.strip() and not NON_PROSE_LINE.match(line)
        ]
        if lines:
            paragraphs.append(" ".join(line.strip() for line in lines))
    return paragraphs


def sentences(prose: str) -> list[str]:
    """Sentences of a prose string, terminators and wrapping quotes stripped."""
    found = []
    for chunk in SENTENCE_SPLIT.split(prose):
        cleaned = SENTENCE_TRAILING.sub("", chunk.strip()).strip()
        if cleaned:
            found.append(cleaned)
    return found


def lexical_words(prose: str) -> list[str]:
    """Lowercased alphabetic words, for vocabulary and adverb metrics."""
    return [match.group(0).lower() for match in LEXICAL_WORD.finditer(prose)]


def adverb_rate(prose: str, total_words: int) -> float:
    """`-ly` adverbs per 1000 words — the most reliable AI-prose tell."""
    if total_words == 0:
        return 0.0
    adverbs = [
        word
        for word in lexical_words(prose)
        if word.endswith("ly") and len(word) > 3 and word not in NON_ADVERB_LY
    ]
    return len(adverbs) * 1000 / total_words


def type_token_ratio(prose: str) -> float:
    """Unique words / total words. Falls with length; compare like for like."""
    words = lexical_words(prose)
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def dialogue_ratio(prose: str, total_words: int) -> float:
    """Share of words inside double quotes. Unclosed quotes count as none."""
    if total_words == 0:
        return 0.0
    quoted = sum(word_count(match.group(0)) for match in DIALOGUE_SPAN.finditer(prose))
    return quoted / total_words


def repeated_openings(sentence_list: list[str], minimum: int = 2) -> dict[str, int]:
    """First words used to open `minimum`+ sentences — the "He …" pileup."""
    openings = Counter()
    for sentence in sentence_list:
        words = lexical_words(sentence)
        if words:
            openings[words[0]] += 1
    return {
        word: count
        for word, count in sorted(
            openings.items(), key=lambda item: (-item[1], item[0])
        )
        if count >= minimum
    }


def banned_phrase_pattern(entry: str) -> str:
    """The literal text to search for in one style-guide bullet.

    Bullets mix literal phrases (`a testament to`) with descriptions of a
    misuse (`"dance" as a verb for non-dancers`). When a bullet quotes a
    fragment, that fragment is the pattern; otherwise the whole bullet is.
    """
    quoted = QUOTED_FRAGMENT.search(entry)
    return (quoted.group(1) if quoted else entry).strip()


def banned_phrase_hits(prose: str, phrases: list[str]) -> dict[str, int]:
    """Case-insensitive whole-word hits, keyed by the original bullet text."""
    hits: dict[str, int] = {}
    for entry in phrases:
        pattern = banned_phrase_pattern(entry)
        if not pattern:
            continue
        found = re.findall(rf"\b{re.escape(pattern)}\b", prose, flags=re.IGNORECASE)
        if found:
            hits[entry] = len(found)
    return hits


def compute_metrics(
    body: str,
    banned: list[str] | None = None,
    target_words: int | None = None,
) -> ChapterMetrics:
    """Every specs §14 metric for one chapter body."""
    paragraphs = prose_paragraphs(body)
    prose = "\n\n".join(paragraphs)
    total_words = word_count(prose)

    sentence_list = [s for paragraph in paragraphs for s in sentences(paragraph)]
    sentence_lengths = [word_count(s) for s in sentence_list]
    paragraph_lengths = [word_count(p) for p in paragraphs]

    per_1000 = (lambda n: n * 1000 / total_words) if total_words else (lambda n: 0.0)

    return ChapterMetrics(
        word_count=total_words,
        target_words=target_words,
        words_vs_target=(total_words / target_words if target_words else None),
        sentence_count=len(sentence_list),
        sentence_length_mean=(
            statistics.fmean(sentence_lengths) if sentence_lengths else 0.0
        ),
        sentence_length_stdev=(
            statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
        ),
        adverb_rate_per_1000=adverb_rate(prose, total_words),
        type_token_ratio=type_token_ratio(prose),
        dialogue_ratio=dialogue_ratio(prose, total_words),
        em_dash_rate_per_1000=per_1000(prose.count("—")),
        semicolon_rate_per_1000=per_1000(prose.count(";")),
        paragraph_count=len(paragraphs),
        paragraph_length_mean=(
            statistics.fmean(paragraph_lengths) if paragraph_lengths else 0.0
        ),
        paragraph_length_max=(max(paragraph_lengths) if paragraph_lengths else 0),
        paragraph_lengths=paragraph_lengths,
        banned_phrase_hits=banned_phrase_hits(prose, banned or []),
        repeated_openings=repeated_openings(sentence_list),
    )
