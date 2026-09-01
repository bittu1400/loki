"""The append primitives: the only way canon ever grows (invariant 1).

Every test here is really one of two questions — does the line read back
through the parser that will retrieve it, and did anything else in the
file move."""

import shutil
from pathlib import Path

import pytest

from novel_engine.core.context_builder import parse_facts, recent_summaries
from novel_engine.core.errors import ContextError, VaultError
from novel_engine.core.vault import (
    append_deepen_question,
    append_fact,
    append_summary,
    append_thread,
    flip_thread_status,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    return copied


def tracker(root: Path) -> str:
    return (root / "canon" / "continuity-tracker.md").read_text(encoding="utf-8")


def threads(root: Path) -> str:
    return (root / "canon" / "open-threads.md").read_text(encoding="utf-8")


def queue(root: Path) -> str:
    return (root / "canon" / "deepen-queue.md").read_text(encoding="utf-8")


def summaries(root: Path) -> str:
    return (root / "log" / "chapter-summary.md").read_text(encoding="utf-8")


# --- facts ------------------------------------------------------------------


def test_appended_fact_round_trips_through_parse_facts(book_root: Path) -> None:
    before = parse_facts(tracker(book_root))
    line = append_fact(
        book_root, "character", "ovist-rhoam", 5, "Ovist reads the ebb ledge at dusk."
    )

    after = parse_facts(tracker(book_root))
    assert len(after) == len(before) + 1
    assert after[-1].raw == line
    assert after[-1].category == "character:ovist-rhoam"
    assert after[-1].entity == "ovist-rhoam"
    assert after[-1].chapter == 5
    assert after[-1].origin == "model"
    assert after[-1].text == "Ovist reads the ebb ledge at dusk."


def test_unscoped_fact_carries_no_entity_qualifier(book_root: Path) -> None:
    line = append_fact(book_root, "world", "", 5, "Lead seals are Office issue.")
    assert line.startswith("- `[world]` `[ch-005]` `[model]` ")


def test_appends_land_inside_the_markers_and_move_nothing_else(book_root: Path) -> None:
    before = tracker(book_root).splitlines()
    line = append_fact(book_root, "timeline", "", 5, "The seal was struck this spring.")
    after = tracker(book_root).splitlines()

    end = after.index("<!-- FACTS:END -->")
    assert after[end - 1] == line
    assert after[: end - 1] + after[end:] == before


def test_engine_appended_facts_are_always_model_origin(book_root: Path) -> None:
    """Pitfall A4: there is no code path that writes `[author]`."""
    line = append_fact(book_root, "world", "", 5, "Something the model noticed.")
    assert "`[model]`" in line
    assert "`[author]`" not in line


@pytest.mark.parametrize(
    "text",
    ["", "   ", "two\nlines", "a <!-- FACTS:END --> escape"],
)
def test_facts_that_would_break_the_ledger_are_refused(book_root: Path, text) -> None:
    before = tracker(book_root)
    with pytest.raises(VaultError):
        append_fact(book_root, "world", "", 5, text)
    assert tracker(book_root) == before


def test_duplicate_fact_is_refused_not_silently_repeated(book_root: Path) -> None:
    append_fact(book_root, "world", "", 5, "The tide turned early.")
    before = tracker(book_root)
    with pytest.raises(VaultError, match="duplicate"):
        append_fact(book_root, "world", "", 5, "The tide turned early.")
    assert tracker(book_root) == before


def test_an_already_malformed_ledger_is_not_appended_to(book_root: Path) -> None:
    path = book_root / "canon" / "continuity-tracker.md"
    path.write_text(
        tracker(book_root).replace(
            "<!-- FACTS:END -->", "- a line that is not a fact\n<!-- FACTS:END -->"
        ),
        encoding="utf-8",
    )
    before = tracker(book_root)
    with pytest.raises(ContextError):
        append_fact(book_root, "world", "", 5, "A new fact.")
    assert tracker(book_root) == before


def test_missing_markers_refuse_before_writing(book_root: Path) -> None:
    path = book_root / "canon" / "continuity-tracker.md"
    path.write_text(tracker(book_root).replace("<!-- FACTS:END -->", ""), "utf-8")
    before = tracker(book_root)
    with pytest.raises((VaultError, ContextError)):
        append_fact(book_root, "world", "", 5, "A new fact.")
    assert tracker(book_root) == before


# --- threads ----------------------------------------------------------------


def test_thread_id_is_allocated_above_the_highest_ever_used(book_root: Path) -> None:
    assert append_thread(book_root, 5, "Someone reset the ebb ledge.") == "T-004"
    assert append_thread(book_root, 5, "The lamp did not sink.") == "T-005"
    assert "- `[T-004]` `[open]` `[ch-005]` Someone reset the ebb ledge." in threads(
        book_root
    )


def test_resolved_threads_keep_their_number(book_root: Path) -> None:
    """IDs do not repeat under engine operation: a resolved thread keeps
    its line, so its number is never free to reissue. (An author who
    deletes a line by hand does free it — the engine cannot see that.)"""
    flip_thread_status(book_root, "T-003", 5)
    assert append_thread(book_root, 5, "A new thread.") == "T-004"


def test_flip_marks_resolved_and_rewrites_nothing_else(book_root: Path) -> None:
    before = threads(book_root).splitlines()
    flip_thread_status(book_root, "T-002", 5)
    after = threads(book_root).splitlines()

    differing = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert len(differing) == 1
    old, new = differing[0]
    assert "`[open]`" in old and "`[resolved:ch-005]`" in new
    assert old.replace("`[open]`", "`[resolved:ch-005]`") == new


def test_flip_refuses_unknown_and_already_resolved_threads(book_root: Path) -> None:
    before = threads(book_root)
    with pytest.raises(VaultError, match="no thread"):
        flip_thread_status(book_root, "T-099", 5)
    with pytest.raises(VaultError, match="already"):
        flip_thread_status(book_root, "T-001", 5)  # resolved:ch-002 in the fixture
    assert threads(book_root) == before


def test_malformed_thread_line_refuses_the_whole_file(book_root: Path) -> None:
    path = book_root / "canon" / "open-threads.md"
    path.write_text(
        threads(book_root).replace(
            "<!-- THREADS:END -->", "- `[T-009]` broken\n<!-- THREADS:END -->"
        ),
        encoding="utf-8",
    )
    before = threads(book_root)
    with pytest.raises(VaultError, match="thread grammar"):
        append_thread(book_root, 5, "A new thread.")
    assert threads(book_root) == before


# --- deepen queue -----------------------------------------------------------


def test_appended_question_is_open_and_chapter_tagged(book_root: Path) -> None:
    line = append_deepen_question(book_root, 5, "Who issues the lead seals?")
    assert line == "- `[open]` `[ch-005]` Who issues the lead seals?"
    assert line in queue(book_root).splitlines()


def test_queue_append_preserves_the_answered_entry(book_root: Path) -> None:
    before = queue(book_root).splitlines()
    append_deepen_question(book_root, 5, "Who issues the lead seals?")
    after = queue(book_root).splitlines()
    assert [line for line in before if "answered:" in line] == [
        line for line in after if "answered:" in line
    ]


# --- summaries --------------------------------------------------------------


def test_summary_appends_one_entry_in_chapter_order(book_root: Path) -> None:
    before = recent_summaries(summaries(book_root), -1)
    paragraph = "Ovist reaches the ebb ledge before dawn and finds the seal."
    append_summary(book_root, 6, paragraph)

    after = recent_summaries(summaries(book_root), -1)
    assert len(after) == len(before) + 1
    assert after[-1].chapter == 6
    assert after[-1].paragraph == paragraph
    assert summaries(book_root).startswith(
        (FIXTURE / "log" / "chapter-summary.md")
        .read_text(encoding="utf-8")
        .rstrip("\n")
    )


def test_summary_refuses_a_second_paragraph_for_one_chapter(book_root: Path) -> None:
    before = summaries(book_root)
    with pytest.raises(VaultError, match="already has a summary"):
        append_summary(book_root, 1, "A rival account of chapter one.")
    assert summaries(book_root) == before


def test_summary_refuses_to_go_backwards(book_root: Path) -> None:
    append_summary(book_root, 6, "Chapter six happens.")
    before = summaries(book_root)
    with pytest.raises(VaultError, match="chapter order"):
        append_summary(book_root, 5, "Chapter five, late.")
    assert summaries(book_root) == before


def test_summary_cannot_forge_a_heading(book_root: Path) -> None:
    before = summaries(book_root)
    with pytest.raises(VaultError, match="forge"):
        append_summary(book_root, 6, "Real paragraph.\n\n## ch-007\nInvented.")
    assert summaries(book_root) == before


def test_empty_summary_is_refused(book_root: Path) -> None:
    with pytest.raises(VaultError, match="empty"):
        append_summary(book_root, 6, "   \n")


# --- the shape of the whole module ------------------------------------------


def test_vault_exposes_no_general_canon_writer() -> None:
    """CLAUDE.md's structural fact, asserted rather than remembered."""
    import novel_engine.core.vault as vault

    public = {name for name in dir(vault) if not name.startswith("_")}
    writers = {name for name in public if name.startswith(("write", "append", "flip"))}
    assert writers == {
        "write_chapter",
        "append_fact",
        "append_thread",
        "append_summary",
        "append_deepen_question",
        "flip_manifest_status",
        "flip_thread_status",
    }
