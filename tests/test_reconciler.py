"""Applying a validated delta: all of it, or none of it.

Half of these tests assert that nothing happened. That is the point —
invariant 2 says an apply that cannot finish must leave canon byte-
identical, and the only way to know is to hash it before and after."""

import shutil
from pathlib import Path

import pytest

from novel_engine.core.config import load_book_config
from novel_engine.core.context_builder import parse_facts, recent_summaries
from novel_engine.core.errors import VaultError
from novel_engine.core.vault import canon_transaction
from novel_engine.editorial.reconciler import CANON_FILES, Reconciliation, reconcile
from novel_engine.editorial.schema import EditorialDelta

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
FAKE_ENV = {
    key: f"test-{key}"
    for key in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
        "AIHUBMIX_API_KEY",
    )
}
SESSION = "sess-20260901-1200-abcd"

BASE = {
    "chapter_number": 6,
    "continuity_violations": [],
    "new_locked_facts": [
        {
            "category": "character",
            "entity": "ovist-rhoam",
            "fact": "Ovist keeps the ebb ledge in his coat.",
            "source_chapter": 6,
        },
        {
            "category": "object",
            "entity": "",
            "fact": "The lead seal is stamped with a spring date.",
            "source_chapter": 6,
        },
    ],
    "thread_updates": {
        "opened": [{"text": "Someone reset the ebb ledge deliberately."}],
        "progressed": [{"thread_id": "T-003", "note": "Vosk is named again."}],
        "resolved": [{"thread_id": "T-002", "resolved_in_chapter": 6}],
    },
    "chapter_summary": "Ovist read the seal and said nothing about it.",
    "next_step_note": "Sela does not know yet.",
    "deepen_questions": ["Who issues the lead seals?"],
    "suggested_canon_patches": [],
    "beat_adherence": {"hit": True, "notes": "Lands late but lands."},
}


@pytest.fixture
def book(tmp_path: Path):
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    return load_book_config(copied.parent, "example-book", env=FAKE_ENV)


def delta(**overrides) -> EditorialDelta:
    return EditorialDelta.model_validate({**BASE, **overrides})


def canon_bytes(book) -> dict[str, bytes]:
    return {rel: (book.root / rel).read_bytes() for rel in CANON_FILES}


# --- the happy path ---------------------------------------------------------


def test_a_valid_delta_lands_in_every_canon_file(book) -> None:
    before = canon_bytes(book)
    result = reconcile(book, delta(), session_id=SESSION)

    assert isinstance(result, Reconciliation)
    assert result.summary_added is True
    assert len(result.facts_added) == 2
    assert result.threads_opened == ["T-004"]
    assert result.threads_resolved == ["T-002"]
    assert len(result.questions_added) == 1
    assert result.canon_lines_added == 5

    after = canon_bytes(book)
    for relative in CANON_FILES:
        assert after[relative] != before[relative], relative


def test_appended_facts_are_python_built_lines_not_model_text(book) -> None:
    """Invariant 1: the tracker gains exactly two lines, each composed
    from validated fields — never a body the model wrote."""
    before = (book.root / "canon/continuity-tracker.md").read_text().splitlines()
    reconcile(book, delta(), session_id=SESSION)
    after = (book.root / "canon/continuity-tracker.md").read_text().splitlines()

    added = [line for line in after if line not in before]
    assert added == [
        "- `[character:ovist-rhoam]` `[ch-006]` `[model]` "
        "Ovist keeps the ebb ledge in his coat.",
        "- `[object]` `[ch-006]` `[model]` "
        "The lead seal is stamped with a spring date.",
    ]
    # And they read back through the retrieval parser.
    facts = parse_facts((book.root / "canon/continuity-tracker.md").read_text())
    assert [fact.raw for fact in facts[-2:]] == added
    assert all(fact.origin == "model" for fact in facts[-2:])


def test_summary_and_thread_flip_land_where_the_readers_look(book) -> None:
    reconcile(book, delta(), session_id=SESSION)

    entries = recent_summaries((book.root / "log/chapter-summary.md").read_text(), -1)
    assert entries[-1].chapter == 6
    assert entries[-1].paragraph == BASE["chapter_summary"]

    threads = (book.root / "canon/open-threads.md").read_text()
    assert "- `[T-002]` `[resolved:ch-006]`" in threads
    assert "- `[T-004]` `[open]` `[ch-006]` Someone reset the ebb ledge" in threads


def test_progressed_threads_change_no_file(book) -> None:
    """specs §5: a thread's text is never rewritten, and a note is not a
    status. The note reaches the author through the audited delta."""
    threads_before = (book.root / "canon/open-threads.md").read_text()
    reconcile(
        book,
        delta(thread_updates={"progressed": BASE["thread_updates"]["progressed"]}),
        session_id=SESSION,
    )
    threads_after = (book.root / "canon/open-threads.md").read_text()
    assert threads_after == threads_before


# --- all or nothing ---------------------------------------------------------


def test_an_unknown_thread_id_rolls_the_whole_delta_back(book) -> None:
    before = canon_bytes(book)
    bad = delta(
        thread_updates={
            "opened": BASE["thread_updates"]["opened"],
            "resolved": [{"thread_id": "T-099", "resolved_in_chapter": 6}],
        }
    )
    with pytest.raises(VaultError, match="no thread T-099"):
        reconcile(book, bad, session_id=SESSION)

    assert canon_bytes(book) == before


def test_a_failure_late_in_the_delta_undoes_the_early_appends(book) -> None:
    """The summary, both facts and the new thread land first; the flip of
    an already-resolved thread then fails. Nothing may survive."""
    before = canon_bytes(book)
    bad = delta(
        thread_updates={
            "opened": BASE["thread_updates"]["opened"],
            "resolved": [{"thread_id": "T-001", "resolved_in_chapter": 6}],
        }
    )
    with pytest.raises(VaultError, match="already"):
        reconcile(book, bad, session_id=SESSION)

    assert canon_bytes(book) == before


def test_reconciling_the_same_chapter_twice_changes_nothing_the_second_time(
    book,
) -> None:
    reconcile(book, delta(), session_id=SESSION)
    after_first = canon_bytes(book)

    with pytest.raises(VaultError, match="already has a summary"):
        reconcile(book, delta(), session_id="sess-20260901-1300-beef")

    assert canon_bytes(book) == after_first


def test_a_rolled_back_apply_writes_no_patches_report(book) -> None:
    bad = delta(
        suggested_canon_patches=[
            {
                "target_file": "characters/ovist-rhoam.md",
                "rationale": "r",
                "suggested_text": "s",
            }
        ],
        thread_updates={"resolved": [{"thread_id": "T-099", "resolved_in_chapter": 6}]},
    )
    with pytest.raises(VaultError):
        reconcile(book, bad, session_id=SESSION)

    assert not (book.root / "log" / "sessions" / f"{SESSION}-patches.md").exists()


# --- suggestions, not patches -----------------------------------------------


def test_suggested_patches_are_reported_and_never_applied(book) -> None:
    target = book.root / "characters" / "ovist-rhoam.md"
    before = target.read_bytes()
    result = reconcile(
        book,
        delta(
            suggested_canon_patches=[
                {
                    "target_file": "characters/ovist-rhoam.md",
                    "rationale": "He now flinches from worked iron.",
                    "suggested_text": "Adds: flinches from worked iron.",
                }
            ]
        ),
        session_id=SESSION,
    )

    assert result.patches_path is not None
    report = result.patches_path.read_text()
    assert "characters/ovist-rhoam.md" in report
    assert "flinches from worked iron" in report
    assert "never applies" in report
    assert target.read_bytes() == before  # the author-owned file is untouched


def test_no_patches_means_no_report_file(book) -> None:
    result = reconcile(book, delta(), session_id=SESSION)
    assert result.patches_path is None
    assert not (book.root / "log" / "sessions" / f"{SESSION}-patches.md").exists()


# --- the transaction itself -------------------------------------------------


def test_canon_transaction_restores_every_file_it_snapshotted(tmp_path: Path) -> None:
    one, two = tmp_path / "one.md", tmp_path / "two.md"
    one.write_text("original one\n")
    two.write_text("original two\n")

    with pytest.raises(VaultError, match="aborted"), canon_transaction([one, two]):
        one.write_text("clobbered\n")
        two.write_text("clobbered\n")
        raise ValueError("something failed late")

    assert one.read_text() == "original one\n"
    assert two.read_text() == "original two\n"


def test_canon_transaction_keeps_the_snapshot_for_diagnosis(tmp_path: Path) -> None:
    path = tmp_path / "one.md"
    path.write_text("original\n")

    with pytest.raises(VaultError) as exc, canon_transaction([path]):
        raise ValueError("boom")

    snapshot = Path(str(exc.value).rsplit(" ", 1)[-1].rstrip("."))
    assert snapshot.is_dir()
    assert (snapshot / "00-one.md").read_text() == "original\n"


def test_canon_transaction_cleans_up_on_success(tmp_path: Path) -> None:
    path = tmp_path / "one.md"
    path.write_text("original\n")
    with canon_transaction([path]) as scratch:
        path.write_text("changed\n")
    assert path.read_text() == "changed\n"
    assert not scratch.exists()


def test_canon_transaction_refuses_a_missing_file(tmp_path: Path) -> None:
    with (
        pytest.raises(VaultError, match="does not exist"),
        canon_transaction([tmp_path / "absent.md"]),
    ):
        pass
