"""Deterministic entity-disagreement check (decision #39, ADR-0012).

The second class a regex can find without judgement: a locked fact says
OVIST has kept the echo ledger, the chapter says BRANNEC has. Measured
2026-09-04 (OQ-10): the primary editor missed exactly that, twice, at
temperature 0.2, with the violated fact in the same prompt — and both
times proposed the contradicted fact verbatim as a NEW locked fact. One
simulated finding in the prompt turned the same model, same chapter,
into a first-call `critical` catch. The lever is evidence, not wording.

Measures, never judges — the rule `metrics.py` and `continuity_numbers`
both follow. A finding is evidence handed to the editorial prompt, never
a gate on a chapter.

Two deliberate differences from the number check:

- **It scans paragraphs, not sentences.** The planted case put the
  fact's noun phrase in one sentence ("The echo ledger itself had never
  been his.") and the wrong name in the next ("Brannec Tull had kept
  it..."). Sentence-scoped matching missed its own test case; the
  claim an entity check is looking for routinely spans a full stop.
- **It decides by proximity, not by presence.** Suppressing any
  paragraph that also names the fact's own character was the first
  guard tried, and it killed the planted case — that paragraph names
  Brannec AND Ovist, because denying someone a role usually means
  naming them. What separates the two cases is which name the fact's
  own wording sits NEXT to. Measured on the fixture: ch-002's
  "which suited Brannec, who had been unseen at the Office for eleven
  years" restates the fact beside its own subject (suppressed), while
  ch-005's "Brannec Tull had kept it" puts the same wording beside the
  wrong name (reported). Presence alone gave one false positive on the
  committed fixture; proximity gives zero.

Known ceiling, deliberately: this finds a NAME where canon has a
different name, in wording close enough to be about the same claim.
Pronoun-only substitutions ("he had kept it"), roles described without a
name, and characters absent from `characters/index.yaml` are out of
scope and always will be.
"""

from __future__ import annotations

from dataclasses import dataclass

from novel_engine.core.context_builder import FactLine
from novel_engine.quality.continuity_numbers import COMMON, WORD
from novel_engine.quality.metrics import prose_paragraphs, sentences

#: Distinctive words a fact and a paragraph must share, beyond every
#: character name, before a different name in that paragraph is treated
#: as a disagreement rather than two people in one scene. Sensitivity of
#: a string matcher, not a creative threshold (decision #22 governs
#: NUMBERS ABOUT PROSE; this is a number about matching).
MIN_SHARED_WORDS = 3


@dataclass(frozen=True)
class EntityConflict:
    """A locked fact and a chapter paragraph naming different people."""

    fact_character: str
    chapter_character: str
    fact_text: str
    chapter_sentence: str
    shared_words: tuple[str, ...]

    def describe(self) -> str:
        shared = ", ".join(self.shared_words)
        return (
            f"canon attributes this to {self.fact_character}, the chapter "
            f"names {self.chapter_character}\n"
            f"    fact:    {self.fact_text}\n"
            f"    chapter: {self.chapter_sentence}\n"
            f"    shared wording: {shared}"
        )


def name_tokens(character_id: str) -> set[str]:
    """Word forms a kebab-case id can appear as: 'ovist-rhoam' -> ovist, rhoam.

    Ids are the author's own naming (specs §1), so the parts are the
    words the prose uses. A one-part id contributes one token.
    """
    return {part for part in character_id.lower().split("-") if len(part) > 2}


def _named_characters(text: str, character_ids: list[str]) -> set[str]:
    words = {word.group(0).lower() for word in WORD.finditer(text)}
    # A possessive ("Ovist's") loses its tail to the word pattern, so the
    # bare token is what matches.
    return {
        character_id
        for character_id in character_ids
        if name_tokens(character_id) & words
    }


def _nearest_distance(
    text: str, tokens_wanted: set[str], shared: set[str]
) -> int | None:
    """Token distance from the closest name token to the closest shared word.

    The discriminator between "the chapter restates this fact about the
    right person" and "the chapter gives the claim to someone else".
    Measured on the fixture: ch-002 says Sela Vosk pays triple AND that
    this suited Brannec, "who had been unseen at the Office for eleven
    years" — the fact's own wording, next to the fact's own name. The
    shared words are nearer Brannec than Sela, so it is a restatement.
    In the planted ch-005 case the same words sit next to the WRONG
    name ("Brannec Tull had kept it"), which is the whole signal.
    """
    words = [word.group(0).lower() for word in WORD.finditer(text)]
    name_positions = [i for i, word in enumerate(words) if word in tokens_wanted]
    shared_positions = [i for i, word in enumerate(words) if word in shared]
    if not name_positions or not shared_positions:
        return None
    return min(
        abs(name_index - shared_index)
        for name_index in name_positions
        for shared_index in shared_positions
    )


def _distinctive_words(text: str, every_name_token: set[str]) -> set[str]:
    return {
        word.group(0).lower()
        for word in WORD.finditer(text)
        if word.group(0).lower() not in COMMON
        and word.group(0).lower() not in every_name_token
    }


def find_entity_conflicts(
    facts: list[FactLine], chapter_body: str, character_ids: list[str]
) -> list[EntityConflict]:
    """Paragraphs that put a different name where a retrieved fact has one.

    Only the facts already retrieved for this chapter are compared — the
    same set the model is shown, so a finding always points at something
    the prompt actually contains.
    """
    conflicts: list[EntityConflict] = []
    seen: set[tuple[str, str, str]] = set()

    every_name_token = {
        token for character_id in character_ids for token in name_tokens(character_id)
    }

    subjects = []
    for fact in facts:
        named = _named_characters(fact.text, character_ids)
        if fact.entity:
            named.add(fact.entity)
        if not named:
            continue
        subjects.append((fact, named, _distinctive_words(fact.text, every_name_token)))

    if not subjects:
        return conflicts

    for paragraph in prose_paragraphs(chapter_body):
        paragraph_names = _named_characters(paragraph, character_ids)
        if not paragraph_names:
            continue
        paragraph_words = _distinctive_words(paragraph, every_name_token)

        for fact, fact_names, fact_words in subjects:
            others = paragraph_names - fact_names
            if not others:
                continue
            shared = fact_words & paragraph_words
            if len(shared) < MIN_SHARED_WORDS:
                continue

            # Whichever name the fact's own wording sits closest to is the
            # one the paragraph is making the claim about. If that is the
            # fact's own character, the paragraph agrees with canon and
            # merely mentions someone else in passing.
            own_tokens = {token for name in fact_names for token in name_tokens(name)}
            other_tokens = {token for name in others for token in name_tokens(name)}
            own_distance = _nearest_distance(paragraph, own_tokens, shared)
            other_distance = _nearest_distance(paragraph, other_tokens, shared)
            if other_distance is None:
                continue
            if own_distance is not None and own_distance <= other_distance:
                continue

            other = sorted(others)[0]
            quote = next(
                (
                    sentence.strip()
                    for sentence in sentences(paragraph)
                    if other in _named_characters(sentence, character_ids)
                ),
                paragraph.strip(),
            )
            key = (sorted(fact_names)[0], other, fact.text)
            if key in seen:
                continue
            seen.add(key)
            conflicts.append(
                EntityConflict(
                    fact_character=sorted(fact_names)[0],
                    chapter_character=other,
                    fact_text=fact.text,
                    chapter_sentence=quote,
                    shared_words=tuple(sorted(shared)),
                )
            )
    return conflicts


def render_entity_conflicts(conflicts: list[EntityConflict]) -> str:
    """The findings as prompt evidence, or an explicit 'none' line."""
    if not conflicts:
        return (
            "- no paragraph names a different character where a locked fact "
            "names one. This check only sees names it can match to "
            "characters/index.yaml; it is not a continuity review."
        )
    return "\n".join(f"- {conflict.describe()}" for conflict in conflicts)
