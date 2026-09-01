"""Pydantic models for the editorial delta (specs.md §12).

Pure validation. No IO, no provider imports, no vault knowledge — this
module decides only whether a blob of model output is a delta, never
what to do with one.

The delta is the ONLY thing an editorial model is allowed to return
(invariant 1, pitfall A1): never a canon file body. Everything that will
end up on a canon line is validated here into the exact shape
`core/vault.py` can compose a line from, so the reconciler never has to
inspect model text again.

Strictness policy:
- `extra="forbid"` everywhere. An unrecognised key means the model
  answered a different question than the one we asked.
- Scalar top-level fields are REQUIRED; the collection fields default to
  empty. A chapter that raised no violation and opened no thread is the
  normal case, and spending a repair attempt on an omitted empty list
  would burn the scarcest quota in the stack to learn nothing.
- Anything destined for a canon line must be single-line and free of
  HTML comment syntax: a fact containing `<!-- FACTS:END -->` would
  otherwise close the section it was appended to.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from novel_engine.core.errors import EditorialError

#: `character:<id>` qualifiers and the `entity` field share this shape.
ENTITY_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
#: `T-` plus a zero-padded counter, allocated by the engine (specs.md §5).
THREAD_ID = re.compile(r"^T-\d{3,}$")

FACT_CATEGORIES = ("world", "character", "magic", "timeline", "object", "location")

_FENCE = re.compile(r"^\s*```(?:json|jsonc)?\s*\n(?P<body>.*?)\n\s*```\s*$", re.DOTALL)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ChapterNumber = Annotated[int, Field(ge=1)]
ThreadId = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=THREAD_ID.pattern)
]


def _canon_line_text(value: str) -> str:
    """Reject text that cannot survive as one line inside a marker block."""
    if "\n" in value or "\r" in value:
        raise ValueError("must be a single line; it becomes one canon line")
    if "<!--" in value or "-->" in value:
        raise ValueError(
            "must not contain HTML comment syntax; it would break the "
            "marker block it is appended inside"
        )
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContinuityViolation(_Strict):
    severity: Literal["critical", "warning"]
    violated_fact: Text
    chapter_excerpt: Text
    explanation: Text


class NewLockedFact(_Strict):
    """One proposed line for `canon/continuity-tracker.md` (specs.md §4).

    `origin` is not a field: every fact arriving through this schema came
    from a model, and the reconciler tags it `[model]` unconditionally.
    A model that could claim `[author]` would defeat pitfall A4.
    """

    category: Literal[FACT_CATEGORIES]  # type: ignore[valid-type]
    entity: str = ""
    fact: Text
    source_chapter: ChapterNumber

    _single_line = field_validator("fact")(_canon_line_text)

    @model_validator(mode="after")
    def _entity_matches_category(self) -> NewLockedFact:
        entity = self.entity.strip()
        if self.category == "character":
            if not ENTITY_ID.fullmatch(entity):
                raise ValueError(
                    "category 'character' needs an entity id in the form "
                    f"'ovist-rhoam'; got {self.entity!r}"
                )
        elif entity:
            raise ValueError(
                f"category {self.category!r} is not entity-scoped, so entity "
                f"must be empty; got {self.entity!r}"
            )
        self.entity = entity
        return self


class OpenedThread(_Strict):
    text: Text

    _single_line = field_validator("text")(_canon_line_text)


class ProgressedThread(_Strict):
    """A thread that moved but did not close.

    Nothing is appended for these — the thread text is never rewritten
    (specs.md §5). The note reaches the author through the session
    report, so it is not constrained to one canon line.
    """

    thread_id: ThreadId
    note: Text


class ResolvedThread(_Strict):
    thread_id: ThreadId
    resolved_in_chapter: ChapterNumber


class ThreadUpdates(_Strict):
    opened: list[OpenedThread] = Field(default_factory=list)
    progressed: list[ProgressedThread] = Field(default_factory=list)
    resolved: list[ResolvedThread] = Field(default_factory=list)


class CanonPatch(_Strict):
    """A SUGGESTION about an author-owned file. Never applied.

    `target_file` is written into `log/sessions/<id>-patches.md` as text
    and is never used as a write path (threat-model.md §6). It is
    validated as a vault-relative path anyway: the one place a model
    could reach for `../../.ssh/config` is a field named after a file.
    """

    target_file: Text
    rationale: Text
    suggested_text: Text

    @field_validator("target_file")
    @classmethod
    def _relative_inside_book(cls, value: str) -> str:
        if value.startswith("/") or value.startswith("~") or ":" in value:
            raise ValueError(f"must be a book-relative path; got {value!r}")
        if ".." in value.split("/"):
            raise ValueError(f"must not climb out of the book; got {value!r}")
        return value


class BeatAdherence(_Strict):
    hit: bool
    notes: Text


class EditorialDelta(_Strict):
    """The whole validated delta. The reconciler accepts nothing else."""

    chapter_number: ChapterNumber
    continuity_violations: list[ContinuityViolation] = Field(default_factory=list)
    new_locked_facts: list[NewLockedFact] = Field(default_factory=list)
    thread_updates: ThreadUpdates = Field(default_factory=ThreadUpdates)
    chapter_summary: Text
    next_step_note: Text
    deepen_questions: list[Annotated[Text, Field()]] = Field(default_factory=list)
    suggested_canon_patches: list[CanonPatch] = Field(default_factory=list)
    beat_adherence: BeatAdherence

    @field_validator("deepen_questions")
    @classmethod
    def _questions_single_line(cls, value: list[str]) -> list[str]:
        return [_canon_line_text(item) for item in value]

    @model_validator(mode="after")
    def _chapters_agree(self) -> EditorialDelta:
        """No line may claim a chapter the pass was not looking at.

        A fact tagged with a future chapter would be retrieved as
        established canon for chapters that have not been written; a
        thread can only be resolved by the chapter under review.
        """
        for item in self.new_locked_facts:
            if item.source_chapter > self.chapter_number:
                raise ValueError(
                    f"new_locked_facts: source_chapter {item.source_chapter} is "
                    f"ahead of the chapter under review ({self.chapter_number})"
                )
        for resolved in self.thread_updates.resolved:
            if resolved.resolved_in_chapter != self.chapter_number:
                raise ValueError(
                    f"thread_updates.resolved: {resolved.thread_id} claims "
                    f"resolution in chapter {resolved.resolved_in_chapter}, but "
                    f"this pass is reviewing chapter {self.chapter_number}"
                )
        seen: set[str] = set()
        for update in (*self.thread_updates.progressed, *self.thread_updates.resolved):
            if update.thread_id in seen:
                raise ValueError(
                    f"thread_updates: {update.thread_id} appears twice; a "
                    "thread gets one outcome per chapter"
                )
            seen.add(update.thread_id)
        return self


def parse_delta(raw: str, *, chapter_number: int | None = None) -> EditorialDelta:
    """Model output -> validated delta, or EditorialError.

    Fails closed for the caller: there is no partial return value, so a
    pass_runner that forgets to handle the error cannot proceed with
    half a delta (invariant 2). The message is written to be quoted
    straight back to the model in the repair prompt, so it names the
    field and what was wrong with it.
    """
    text = raw.strip()
    fenced = _FENCE.match(text)
    if fenced:
        # Models wrap JSON in ```json fences constantly. Burning a repair
        # attempt on punctuation teaches nothing and costs a call.
        text = fenced.group("body").strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EditorialError(f"Editorial response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise EditorialError(
            f"Editorial response must be a JSON object, got {type(payload).__name__}."
        )

    try:
        delta = EditorialDelta.model_validate(payload)
    except ValidationError as exc:
        problems = "\n".join(
            f"  - {'.'.join(str(part) for part in error['loc']) or '<root>'}: "
            f"{error['msg']}"
            for error in exc.errors()
        )
        raise EditorialError(
            f"Editorial response does not match the delta schema "
            f"(specs.md §12):\n{problems}"
        ) from exc

    if chapter_number is not None and delta.chapter_number != chapter_number:
        raise EditorialError(
            f"Editorial response is about chapter {delta.chapter_number}, but "
            f"the pass is reviewing chapter {chapter_number}."
        )
    return delta
