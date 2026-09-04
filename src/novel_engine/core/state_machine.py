"""Session state machine: status transitions, resume, idempotency.

Specs §8 defines the log/next-step.md frontmatter contract and prose note.
Specs §11 defines the phase lifecycle:
    target -> drafted -> styled -> [editorial-pending | reconciled] -> complete
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from novel_engine.core.errors import ContextError, StateMachineError

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


# --- phase transitions ------------------------------------------------------

LEGAL_TRANSITIONS: dict[SessionPhase, frozenset[SessionPhase]] = {
    "complete": frozenset({"target"}),
    "target": frozenset({"target", "drafted"}),
    "drafted": frozenset({"styled"}),
    # styled -> complete is the editorial-disabled escape (decision #36):
    # the only route to `complete` that writes no canon. Without it a book
    # with `editorial.enabled: false` parks its pointer at `styled` and
    # every later run resumes the same chapter forever.
    "styled": frozenset({"editorial-pending", "reconciled", "complete"}),
    "editorial-pending": frozenset({"editorial-pending", "reconciled"}),
    "reconciled": frozenset({"complete"}),
}


def validate_transition(current: SessionPhase, target: SessionPhase) -> None:
    """Validate that moving from current to target is a legal lifecycle step.

    Raises StateMachineError if the transition is illegal according to specs §11.
    """
    allowed = LEGAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        options = ", ".join(f"'{p}'" for p in sorted(allowed)) or "none"
        raise StateMachineError(
            f"Illegal session phase transition from '{current}' to '{target}'. "
            f"Legal transitions from '{current}' are: {options}."
        )


def build_next_step(
    current: NextStep,
    target_phase: SessionPhase,
    *,
    session_id: str | None = None,
    status: str | None = None,
    chapter: int | None = None,
    pov: str | None = None,
    note: str | None = None,
    blocked: bool | None = None,
    blocked_reason: str | None = None,
) -> NextStep:
    """Construct an updated NextStep for the target phase without writing to disk.

    Enforces transition validity and blocker rules.
    """
    if current.blocked and blocked is not False:
        reason = current.blocked_reason or "no reason given"
        raise StateMachineError(
            f"Session is blocked: {reason}. Resolve the blocker before transitioning."
        )

    validate_transition(current.last_session_phase, target_phase)

    return NextStep(
        next_chapter=chapter if chapter is not None else current.next_chapter,
        next_pov=pov if pov is not None else current.next_pov,
        last_session_id=(
            session_id if session_id is not None else current.last_session_id
        ),
        last_session_phase=target_phase,
        last_session_status=(
            status if status is not None else current.last_session_status
        ),
        blocked=blocked if blocked is not None else current.blocked,
        blocked_reason=(
            blocked_reason if blocked_reason is not None else current.blocked_reason
        ),
        note=note if note is not None else current.note,
    )


class SessionStateMachine:
    """Manages session lifecycle and phase persistence for a book vault."""

    def __init__(self, book_root: Path, current: NextStep) -> None:
        self.book_root = book_root
        self.current = current

    @classmethod
    def load(cls, book_root: Path) -> SessionStateMachine:
        """Load state machine from book_root/log/next-step.md."""
        from novel_engine.core.vault import read_next_step

        return cls(book_root, read_next_step(book_root))

    @property
    def phase(self) -> SessionPhase:
        return self.current.last_session_phase

    @property
    def is_blocked(self) -> bool:
        return self.current.blocked

    def transition(
        self,
        target_phase: SessionPhase,
        *,
        session_id: str | None = None,
        status: str | None = None,
        chapter: int | None = None,
        pov: str | None = None,
        note: str | None = None,
        blocked: bool | None = None,
        blocked_reason: str | None = None,
    ) -> NextStep:
        """Persist phase transition to log/next-step.md before next phase begins.

        Specs §11: Every phase transition is persisted to log/next-step.md before
        the next phase begins. A crash between phases is therefore always resumable.
        """
        from novel_engine.core.vault import write_next_step

        new_step = build_next_step(
            self.current,
            target_phase,
            session_id=session_id,
            status=status,
            chapter=chapter,
            pov=pov,
            note=note,
            blocked=blocked,
            blocked_reason=blocked_reason,
        )
        write_next_step(self.book_root, new_step)
        self.current = new_step
        return self.current

    def restart(self, *, chapter: int, pov: str, session_id: str) -> NextStep:
        """Abandon an interrupted session and re-enter `target` for a chapter.

        The one write that does not validate a transition, because it is not
        one: it is the author saying "throw this session away" through
        `--force`, which already costs a typed confirmation at the CLI and
        replaces the prose itself (decision #38, invariant 5). The automatic
        path never calls it.
        """
        from novel_engine.core.vault import write_next_step

        new_step = NextStep(
            next_chapter=chapter,
            next_pov=pov,
            last_session_id=session_id,
            last_session_phase="target",
            last_session_status="restarted",
            note=self.current.note,
        )
        write_next_step(self.book_root, new_step)
        self.current = new_step
        return self.current

    def mark_blocked(self, reason: str) -> NextStep:
        """Mark the session as blocked with an actionable explanation."""
        from novel_engine.core.vault import write_next_step

        new_step = self.current.model_copy(
            update={"blocked": True, "blocked_reason": reason}
        )
        write_next_step(self.book_root, new_step)
        self.current = new_step
        return self.current

    def unblock(self) -> NextStep:
        """Clear the blocked flag on the session pointer."""
        from novel_engine.core.vault import write_next_step

        new_step = self.current.model_copy(
            update={"blocked": False, "blocked_reason": ""}
        )
        write_next_step(self.book_root, new_step)
        self.current = new_step
        return self.current
