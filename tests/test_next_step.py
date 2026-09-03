"""Tests for log/next-step.md frontmatter contract, parser, and vault primitives.
See specs §8.
"""

import shutil
from pathlib import Path

import pytest

from novel_engine.core.errors import ContextError, VaultError
from novel_engine.core.state_machine import (
    NextStep,
    parse_next_step,
    serialize_next_step,
)
from novel_engine.core.vault import next_step_path, read_next_step, write_next_step

FIXTURE_BOOK = Path(__file__).resolve().parents[1] / "vault" / "example-book"
TEMPLATE_NEXT_STEP = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "novel_engine"
    / "templates"
    / "book"
    / "log"
    / "next-step.md"
)


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE_BOOK, copied)
    return copied


def test_parse_fixture_next_step() -> None:
    text = (FIXTURE_BOOK / "log" / "next-step.md").read_text(encoding="utf-8")
    step = parse_next_step(text)
    assert step.next_chapter == 3
    assert step.next_pov == "ovist-rhoam"
    assert step.last_session_id == "sess-20260822-0915-b7e2"
    assert step.last_session_phase == "complete"
    assert step.last_session_status == "pending-review"
    assert step.blocked is False
    assert step.blocked_reason == ""
    assert "Ovist has a forged correction" in step.note


def test_parse_template_next_step() -> None:
    text = TEMPLATE_NEXT_STEP.read_text(encoding="utf-8")
    step = parse_next_step(text)
    assert step.next_chapter == 1
    assert step.next_pov == ""
    assert step.last_session_id == ""
    assert step.last_session_phase == "complete"
    assert step.last_session_status == "not-started"
    assert step.blocked is False
    assert step.blocked_reason == ""
    assert "Operational pointer and resume state." in step.note


def test_parse_rejects_missing_frontmatter() -> None:
    with pytest.raises(ContextError, match="does not start with frontmatter"):
        parse_next_step("Just some prose without frontmatter")


def test_parse_rejects_unclosed_frontmatter() -> None:
    with pytest.raises(ContextError, match="frontmatter is not closed"):
        parse_next_step("---\nnext_chapter: 1\nno closing marker")


def test_parse_rejects_invalid_yaml() -> None:
    with pytest.raises(ContextError, match="not valid YAML"):
        parse_next_step("---\n: invalid: yaml: [}\n---\n")


def test_parse_rejects_non_mapping_yaml() -> None:
    with pytest.raises(ContextError, match="must be a YAML mapping"):
        parse_next_step("---\n- item 1\n- item 2\n---\n")


def test_parse_rejects_extra_fields() -> None:
    text = (
        "---\n"
        "next_chapter: 1\n"
        "next_pov: 'kaelen'\n"
        "last_session_id: 'sess-123'\n"
        "last_session_phase: 'target'\n"
        "last_session_status: 'draft'\n"
        "blocked: false\n"
        "blocked_reason: ''\n"
        "unrecognized_field: true\n"
        "---\n"
    )
    with pytest.raises(ContextError, match="failed validation"):
        parse_next_step(text)


def test_parse_rejects_invalid_phase() -> None:
    text = (
        "---\n"
        "next_chapter: 1\n"
        "next_pov: 'kaelen'\n"
        "last_session_id: 'sess-123'\n"
        "last_session_phase: 'invented-phase'\n"
        "last_session_status: 'draft'\n"
        "blocked: false\n"
        "blocked_reason: ''\n"
        "---\n"
    )
    with pytest.raises(ContextError, match="failed validation"):
        parse_next_step(text)


def test_parse_rejects_chapter_below_one() -> None:
    text = (
        "---\n"
        "next_chapter: 0\n"
        "next_pov: 'kaelen'\n"
        "last_session_id: 'sess-123'\n"
        "last_session_phase: 'target'\n"
        "last_session_status: 'draft'\n"
        "blocked: false\n"
        "blocked_reason: ''\n"
        "---\n"
    )
    with pytest.raises(ContextError, match="failed validation"):
        parse_next_step(text)


def test_parse_coerces_none_to_empty_str() -> None:
    text = (
        "---\n"
        "next_chapter: 2\n"
        "next_pov:\n"
        "last_session_id:\n"
        "last_session_phase: 'target'\n"
        "last_session_status: 'draft'\n"
        "blocked: false\n"
        "blocked_reason:\n"
        "---\n"
    )
    step = parse_next_step(text)
    assert step.next_pov == ""
    assert step.last_session_id == ""
    assert step.blocked_reason == ""


def test_serialize_and_round_trip() -> None:
    original = NextStep(
        next_chapter=14,
        next_pov="lyra",
        last_session_id="sess-20260901-1200-a1b2",
        last_session_phase="styled",
        last_session_status="draft",
        blocked=True,
        blocked_reason="Waiting for author clarification on thread #3",
        note="Lyra reaches the spire before sundown.",
    )
    serialized = serialize_next_step(original)
    assert serialized.startswith("---\n")
    assert "next_chapter: 14\n" in serialized
    assert "last_session_phase: styled\n" in serialized
    assert "blocked: true\n" in serialized
    assert serialized.endswith("Lyra reaches the spire before sundown.\n")

    reparsed = parse_next_step(serialized)
    assert reparsed == original


def test_serialize_empty_note() -> None:
    step = NextStep(
        next_chapter=1,
        last_session_phase="target",
    )
    serialized = serialize_next_step(step)
    assert serialized.endswith("---\n")
    reparsed = parse_next_step(serialized)
    assert reparsed.note == ""
    assert reparsed == step


def test_vault_read_next_step(book_root: Path) -> None:
    step = read_next_step(book_root)
    assert step.next_chapter == 3
    assert step.next_pov == "ovist-rhoam"


def test_vault_read_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(VaultError, match="Missing next-step pointer"):
        read_next_step(tmp_path)


def test_vault_write_next_step(book_root: Path) -> None:
    new_step = NextStep(
        next_chapter=4,
        next_pov="brannec",
        last_session_id="sess-20260903-1100-c4d5",
        last_session_phase="complete",
        last_session_status="pending-review",
        blocked=False,
        blocked_reason="",
        note="Brannec leaves the countersigning rolls locked.",
    )
    path = write_next_step(book_root, new_step)
    assert path == next_step_path(book_root)

    # Re-reading from disk yields exact data
    reread = read_next_step(book_root)
    assert reread == new_step


def test_vault_write_missing_log_dir_raises(tmp_path: Path) -> None:
    step = NextStep(next_chapter=1, last_session_phase="target")
    with pytest.raises(VaultError, match="Missing log directory"):
        write_next_step(tmp_path, step)
