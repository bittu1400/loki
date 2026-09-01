"""Deterministic number-disagreement check (decision #30).

The one class of continuity error a regex can find without judgement: a
locked fact says the page carries TWO corrections, the chapter says
NINE. It was missed twice by a live editor model that had the fact six
lines above the chapter text, which is why it is worth finding in Python
before the call rather than hoping for it after.

Measures, never judges — the same rule `metrics.py` follows. A finding
is evidence handed to the editorial prompt, never a gate on a chapter.

Known ceiling, deliberately: this matches a quantity plus the noun it
counts, and only reports a disagreement when the fact and the chapter
sentence ALSO share at least two other distinctive words. That second
condition is what separates "two corrections on the spring-tide page"
from "nine corrections on the spring-tide page" (shared: corrections,
spring-tide, page) from the four ways ch-005 says a number next to
"years" — "kept the ledger eleven years" against "twelve years of them,
bound in oilcloth", which share one incidental word and nothing else.
One shared word was measured to be too weak on this chapter: it passed
all three year-conflicts through, including the exact false positive a
live model reported. Two is a tuned number, not a discovered one. Rewritten quantities
("a handful", "half a dozen") and numbers separated from their noun by
more than one word are out of scope and always will be; this is a
cheap net for the commonest case, not a continuity engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from novel_engine.core.context_builder import FactLine
from novel_engine.quality.metrics import prose_paragraphs, sentences

NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}

#: A quantity followed by the thing it counts: "nine corrections", "11 years".
QUANTITY = re.compile(
    r"\b(?P<value>\d{1,4}|" + "|".join(NUMBER_WORDS) + r")\b[\s-]+"
    r"(?P<noun>[a-z][a-z'-]{2,})",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-z][a-z'-]{3,}", re.IGNORECASE)

#: Distinctive words a fact and a chapter sentence must share, beyond the
#: counted noun, before their quantities are treated as being about the
#: same thing. Sensitivity of a heuristic, not a creative threshold —
#: decision #22 keeps NUMBERS ABOUT PROSE out of the engine, and this is
#: a number about string matching.
MIN_CORROBORATING_WORDS = 2

#: Words too common to count as corroboration between a fact and a line.
COMMON = {
    "about",
    "after",
    "again",
    "also",
    "another",
    "because",
    "been",
    "before",
    "between",
    "both",
    "could",
    "during",
    "each",
    "every",
    "from",
    "had",
    "hand",
    "hands",
    "has",
    "have",
    "here",
    "into",
    "just",
    "like",
    "made",
    "make",
    "many",
    "more",
    "most",
    "much",
    "only",
    "other",
    "over",
    "said",
    "says",
    "should",
    "some",
    "such",
    "take",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "thing",
    "things",
    "this",
    "those",
    "time",
    "times",
    "told",
    "took",
    "under",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "will",
    "with",
    "without",
    "would",
    "year",
    "years",
}


@dataclass(frozen=True)
class NumberConflict:
    """One quantity in the chapter disagreeing with one in a locked fact."""

    noun: str
    fact_value: int
    chapter_value: int
    fact_text: str
    chapter_sentence: str

    def describe(self) -> str:
        return (
            f'"{self.noun}": canon says {self.fact_value}, the chapter says '
            f"{self.chapter_value}\n"
            f"    fact:    {self.fact_text}\n"
            f"    chapter: {self.chapter_sentence}"
        )


def _value(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token.lower())


def quantities(text: str) -> list[tuple[str, int]]:
    """(noun, value) pairs — 'nine corrections' -> ('correction', 9).

    Nouns are crudely singularised so 'nine corrections' and 'a
    correction' compare equal. Crude is the point: a stemmer would be a
    dependency, and this only has to line two sentences up.
    """
    found: list[tuple[str, int]] = []
    for match in QUANTITY.finditer(text):
        value = _value(match.group("value"))
        if value is None:
            continue
        noun = match.group("noun").lower().rstrip("'")
        if noun in NUMBER_WORDS:  # "two hundred" — the noun is another number
            continue
        found.append((noun.removesuffix("s") or noun, value))
    return found


def _corroborating_words(text: str) -> set[str]:
    return {
        word.group(0).lower()
        for word in WORD.finditer(text)
        if word.group(0).lower() not in COMMON
    }


def find_number_conflicts(
    facts: list[FactLine], chapter_body: str
) -> list[NumberConflict]:
    """Quantities in the chapter that disagree with a retrieved fact.

    Only the facts already retrieved for this chapter are compared — the
    same set the model is shown, so a finding always points at something
    the prompt actually contains.
    """
    conflicts: list[NumberConflict] = []
    seen: set[tuple[str, int, int]] = set()

    fact_quantities = [
        (fact, noun, value, _corroborating_words(fact.text))
        for fact in facts
        for noun, value in quantities(fact.text)
    ]
    if not fact_quantities:
        return conflicts

    for paragraph in prose_paragraphs(chapter_body):
        for sentence in sentences(paragraph):
            sentence_words = _corroborating_words(sentence)
            found_here = quantities(sentence)
            # A sentence that ALSO states the canonical number for the
            # same noun is not contradicting it — "eleven years of his
            # tenure, then one year of his predecessor" agrees with
            # canon and counts a second thing beside it.
            agreed = {noun for noun, value in found_here}
            for noun, value in found_here:
                for fact, fact_noun, fact_value, fact_words in fact_quantities:
                    if fact_noun != noun or fact_value == value:
                        continue
                    if (fact_noun, fact_value) in {
                        pair for pair in found_here if pair[0] in agreed
                    }:
                        continue
                    # The noun alone is not enough: "eleven years" and
                    # "twelve years" are about different things until the
                    # two sentences share more than that.
                    shared = (fact_words & sentence_words) - {noun, noun + "s"}
                    if len(shared) < MIN_CORROBORATING_WORDS:
                        continue
                    key = (noun, fact_value, value)
                    if key in seen:
                        continue
                    seen.add(key)
                    conflicts.append(
                        NumberConflict(
                            noun=noun,
                            fact_value=fact_value,
                            chapter_value=value,
                            fact_text=fact.text,
                            chapter_sentence=sentence.strip(),
                        )
                    )
    return conflicts


def render_conflicts(conflicts: list[NumberConflict]) -> str:
    """The findings as prompt evidence, or an explicit 'none' line."""
    if not conflicts:
        return (
            "- no quantity in the chapter disagrees with a quantity in the "
            "locked facts above. This check only sees numbers next to the "
            "noun they count; it is not a continuity review."
        )
    return "\n".join(f"- {conflict.describe()}" for conflict in conflicts)
