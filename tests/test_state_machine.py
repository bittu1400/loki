"""Tests for the session state machine and lifecycle transitions (specs §11)."""

import shutil
from pathlib import Path

import pytest

from novel_engine.core.errors import StateMachineError
from novel_engine.core.state_machine import (
    LEGAL_TRANSITIONS,
    VALID_PHASES,
    NextStep,
    SessionStateMachine,
    build_next_step,
    validate_transition,
)
from novel_engine.core.vault import read_next_step

ALL_PHASES = (
    "target",
    "drafted",
    "styled",
    "editorial-pending",
    "reconciled",
    "complete",
)

FIXTURE_BOOK = Path(__file__).resolve().parents[1] / "vault" / "example-book"


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE_BOOK, copied)
    return copied


def test_all_legal_transitions_pass_validation() -> None:
    assert frozenset(ALL_PHASES) == VALID_PHASES
    for current, allowed in LEGAL_TRANSITIONS.items():
        for target in allowed:
            validate_transition(current, target)


def test_illegal_transitions_raise_state_machine_error() -> None:
    for current in ALL_PHASES:
        allowed = LEGAL_TRANSITIONS.get(current, frozenset())
        for target in ALL_PHASES:
            if target not in allowed:
                with pytest.raises(
                    StateMachineError, match="Illegal session phase transition"
                ):
                    validate_transition(current, target)


def test_illegal_transition_message_contains_legal_options() -> None:
    with pytest.raises(StateMachineError) as excinfo:
        validate_transition("complete", "drafted")
    msg = str(excinfo.value)
    assert "Illegal session phase transition from 'complete' to 'drafted'" in msg
    assert "Legal transitions from 'complete' are: 'target'" in msg


def test_build_next_step_success() -> None:
    base = NextStep(
        next_chapter=1,
        last_session_phase="complete",
        last_session_status="not-started",
    )
    targeted = build_next_step(
        base,
        "target",
        session_id="sess-20260903-1000-abcd",
        chapter=2,
        pov="kaelen",
        status="draft",
    )
    assert targeted.last_session_phase == "target"
    assert targeted.next_chapter == 2
    assert targeted.next_pov == "kaelen"
    assert targeted.last_session_id == "sess-20260903-1000-abcd"
    assert targeted.last_session_status == "draft"


def test_build_next_step_blocked_refuses_transition() -> None:
    base = NextStep(
        next_chapter=1,
        last_session_phase="complete",
        blocked=True,
        blocked_reason="Waiting for author approval",
    )
    with pytest.raises(StateMachineError, match="Session is blocked"):
        build_next_step(base, "target")


def test_build_next_step_explicit_unblock_succeeds() -> None:
    base = NextStep(
        next_chapter=1,
        last_session_phase="complete",
        blocked=True,
        blocked_reason="Waiting for author approval",
    )
    unblocked = build_next_step(base, "target", blocked=False, blocked_reason="")
    assert unblocked.last_session_phase == "target"
    assert unblocked.blocked is False
    assert unblocked.blocked_reason == ""


def test_state_machine_load(book_root: Path) -> None:
    sm = SessionStateMachine.load(book_root)
    assert sm.phase == "complete"
    assert sm.is_blocked is False
    assert sm.current.next_chapter == 3


def test_full_session_lifecycle_walkthrough(book_root: Path) -> None:
    """Walk the happy path:
    complete -> target -> drafted -> styled -> reconciled -> complete.
    """
    sm = SessionStateMachine.load(book_root)
    assert sm.phase == "complete"

    # Step 3: Target
    sm.transition(
        "target",
        session_id="sess-20260903-1200-test",
        chapter=3,
        pov="ovist-rhoam",
        status="draft",
    )
    assert sm.phase == "target"
    assert read_next_step(book_root).last_session_phase == "target"
    assert read_next_step(book_root).last_session_id == "sess-20260903-1200-test"

    # Step 5: Drafted
    sm.transition("drafted")
    assert sm.phase == "drafted"
    assert read_next_step(book_root).last_session_phase == "drafted"

    # Step 8: Styled
    sm.transition("styled")
    assert sm.phase == "styled"
    assert read_next_step(book_root).last_session_phase == "styled"

    # Step 10: Reconciled
    sm.transition("reconciled")
    assert sm.phase == "reconciled"
    assert read_next_step(book_root).last_session_phase == "reconciled"

    # Step 11: Complete
    sm.transition(
        "complete",
        chapter=4,
        pov="brannec",
        status="pending-review",
        note="Brannec leaves the countersigning rolls locked.",
    )
    assert sm.phase == "complete"
    on_disk = read_next_step(book_root)
    assert on_disk.last_session_phase == "complete"
    assert on_disk.last_session_status == "pending-review"
    assert on_disk.next_chapter == 4
    assert on_disk.next_pov == "brannec"
    assert "Brannec leaves the countersigning rolls locked." in on_disk.note


def test_editorial_pending_branch(book_root: Path) -> None:
    """styled -> editorial-pending -> reconciled -> complete."""
    sm = SessionStateMachine.load(book_root)
    sm.transition("target", session_id="sess-1")
    sm.transition("drafted")
    sm.transition("styled")

    # Editorial fails / critical violation -> editorial-pending
    sm.transition("editorial-pending")
    assert sm.phase == "editorial-pending"
    assert read_next_step(book_root).last_session_phase == "editorial-pending"

    # Retrying fails again -> stays editorial-pending
    sm.transition("editorial-pending")
    assert sm.phase == "editorial-pending"

    # Retrying succeeds -> reconciled -> complete
    sm.transition("reconciled")
    assert sm.phase == "reconciled"
    sm.transition("complete", chapter=4)
    assert sm.phase == "complete"


def test_state_machine_refuses_illegal_transition_and_leaves_disk_untouched(
    book_root: Path,
) -> None:
    sm = SessionStateMachine.load(book_root)
    assert sm.phase == "complete"

    with pytest.raises(StateMachineError, match="Illegal session phase transition"):
        sm.transition("reconciled")

    # In-memory state and disk state are untouched
    assert sm.phase == "complete"
    assert read_next_step(book_root).last_session_phase == "complete"


def test_mark_blocked_and_unblock(book_root: Path) -> None:
    sm = SessionStateMachine.load(book_root)
    sm.mark_blocked("Critical continuity question on character sheet")
    assert sm.is_blocked is True
    assert read_next_step(book_root).blocked is True
    assert "Critical continuity question" in read_next_step(book_root).blocked_reason

    # Further transition is refused while blocked
    with pytest.raises(StateMachineError, match="Session is blocked"):
        sm.transition("target")

    # Unblocking clears it
    sm.unblock()
    assert sm.is_blocked is False
    assert read_next_step(book_root).blocked is False
    assert read_next_step(book_root).blocked_reason == ""

    # Now transition succeeds
    sm.transition("target", session_id="sess-2")
    assert sm.phase == "target"
