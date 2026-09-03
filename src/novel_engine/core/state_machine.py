"""Session state machine: status transitions, resume, idempotency.

Specs §8 defines the log/next-step.md frontmatter contract and prose note.
Specs §11 defines the phase lifecycle:
    target -> drafted -> styled -> [editorial-pending | reconciled] -> complete
"""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from novel_engine.core.errors import ContextError

SessionPhase = Literal[
    "target",
    "drafted",
    "styled",
    "editorial-pending",
    "reconciled",
    "complete",
]

VALID_PHASES: frozenset[SessionPhase] = frozenset(
    {"target", "drafted", "styled", "editorial-pending", "reconciled", "complete"}
)

FRONTMATTER_FIELDS: tuple[str, ...] = (
    "next_chapter",
    "next_pov",
    "last_session_id",
    "last_session_phase",
    "last_session_status",
    "blocked",
    "blocked_reason",
)


class NextStepFrontmatter(BaseModel):
    """Machine contract in log/next-step.md frontmatter (specs.md §8)."""

    model_config = ConfigDict(extra="forbid")

    next_chapter: int
    next_pov: str = ""
    last_session_id: str = ""
    last_session_phase: SessionPhase
    last_session_status: str = "not-started"
    blocked: bool = False
    blocked_reason: str = ""

    @field_validator("next_chapter")
    @classmethod
    def _validate_chapter(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"next_chapter must be >= 1, got {v}")
        return v

    @field_validator("next_pov", "last_session_id", "blocked_reason", mode="before")
    @classmethod
    def _coerce_none_to_empty_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class NextStep(BaseModel):
    """Full log/next-step.md representation: frontmatter contract + prose note."""

    model_config = ConfigDict(extra="forbid")

    next_chapter: int
    next_pov: str = ""
    last_session_id: str = ""
    last_session_phase: SessionPhase
    last_session_status: str = "not-started"
    blocked: bool = False
    blocked_reason: str = ""
    note: str = ""

    @field_validator("next_chapter")
    @classmethod
    def _validate_chapter(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"next_chapter must be >= 1, got {v}")
        return v

    @field_validator("next_pov", "last_session_id", "blocked_reason", mode="before")
    @classmethod
    def _coerce_none_to_empty_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("note", mode="before")
    @classmethod
    def _normalize_note(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()


def parse_next_step(text: str) -> NextStep:
    """Parse log/next-step.md text into a validated NextStep instance.

    Raises ContextError if the frontmatter is missing, malformed YAML,
    or violates the specs §8 schema.
    """
    if not text.startswith("---\n"):
        raise ContextError("log/next-step.md does not start with frontmatter ('---').")
    end = text.find("\n---", 4)
    if end == -1:
        raise ContextError(
            "log/next-step.md frontmatter is not closed by a '---' line."
        )

    raw_yaml = text[4:end]
    try:
        raw_fields = yaml.safe_load(raw_yaml)
    except Exception as exc:
        raise ContextError(
            f"log/next-step.md frontmatter is not valid YAML: {exc}"
        ) from exc

    if not isinstance(raw_fields, dict):
        raise ContextError("log/next-step.md frontmatter must be a YAML mapping.")

    try:
        fm = NextStepFrontmatter(**raw_fields)
    except ValidationError as exc:
        raise ContextError(
            f"log/next-step.md frontmatter failed validation: {exc}"
        ) from exc

    # Note is the markdown body following the closing '---' line
    body_offset = text.find("\n", end + 1)
    body = text[body_offset + 1 :].strip() if body_offset != -1 else ""

    return NextStep(**fm.model_dump(), note=body)


def serialize_next_step(step: NextStep) -> str:
    """Format a NextStep instance into valid markdown with YAML frontmatter."""
    fm_dict = {
        "next_chapter": step.next_chapter,
        "next_pov": step.next_pov,
        "last_session_id": step.last_session_id,
        "last_session_phase": step.last_session_phase,
        "last_session_status": step.last_session_status,
        "blocked": step.blocked,
        "blocked_reason": step.blocked_reason,
    }
    fm_yaml = yaml.safe_dump(fm_dict, sort_keys=False, allow_unicode=True).rstrip("\n")
    if step.note:
        return f"---\n{fm_yaml}\n---\n\n{step.note}\n"
    return f"---\n{fm_yaml}\n---\n"
