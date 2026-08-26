"""Vault write-primitive tests: chapter creation (create-only), the
generated_hash convention against the fixture, resolve_target wiring,
and surgical manifest status flips."""

import shutil
from pathlib import Path

import pytest

from fakes import reset_fixture_state
from novel_engine.core.errors import ConfigError, VaultError
from novel_engine.core.outline import parse_manifest, resolve_target
from novel_engine.core.vault import (
    chapter_path,
    flip_manifest_status,
    generated_hash,
    split_chapter_file,
    write_chapter,
)

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    reset_fixture_state(copied)
    return copied


# --- generated_hash convention ----------------------------------------------


def test_fixture_chapter_hashes_match_convention() -> None:
    """The convention established in Session 2 must still hold for every
    committed fixture chapter — it is the contract write_chapter keeps."""
    for path in sorted((FIXTURE / "chapters").glob("chapter-*.md")):
        fields, body = split_chapter_file(path.read_text(encoding="utf-8"))
        assert fields["generated_hash"] == generated_hash(body)


def test_generated_hash_is_stable_and_prefixed() -> None:
    assert generated_hash("hello\n").startswith("sha256:")
    assert generated_hash("hello\n") == generated_hash("hello\n")


def test_generated_hash_strips_leading_blank_lines() -> None:
    assert generated_hash("\n\nbody") == generated_hash("body")


# --- write_chapter ------------------------------------------------------------


def test_write_chapter_creates_file_with_valid_frontmatter(book_root: Path) -> None:
    body = "# Chapter 3\n\nProse."
    path = write_chapter(
        book_root,
        3,
        {"chapter_number": 3, "pov": "ovist-rhoam"},
        body,
    )
    assert path.exists()
    fields, stored_body = split_chapter_file(path.read_text(encoding="utf-8"))
    assert fields["chapter_number"] == 3
    assert fields["pov"] == "ovist-rhoam"
    # Hash is computed from the body as written, not supplied by the caller.
    assert fields["generated_hash"] == generated_hash(stored_body)
    assert stored_body.lstrip("\n").startswith("# Chapter 3")


def test_write_chapter_refuses_overwrite(book_root: Path) -> None:
    with pytest.raises(VaultError, match="Refusing to overwrite"):
        write_chapter(book_root, 1, {"chapter_number": 1}, "replacement prose")


def test_write_chapter_overwrite_requires_explicit_opt_in(book_root: Path) -> None:
    write_chapter(
        book_root, 1, {"chapter_number": 1}, "replacement prose", allow_overwrite=True
    )
    _, body = split_chapter_file(chapter_path(book_root, 1).read_text())
    assert body.lstrip("\n").startswith("replacement prose")


def test_write_chapter_rejects_caller_supplied_hash(book_root: Path) -> None:
    with pytest.raises(VaultError, match="generated_hash"):
        write_chapter(book_root, 5, {"generated_hash": "sha256:x"}, "body")


def test_write_chapter_missing_directory_fails(tmp_path: Path) -> None:
    empty = tmp_path / "no-chapters-dir"
    empty.mkdir()
    with pytest.raises(VaultError, match="chapters directory"):
        write_chapter(empty, 1, {}, "body")
    assert not list(empty.iterdir())


# --- resolve_target -----------------------------------------------------------


def test_resolve_target_picks_lowest_planned(book_root: Path) -> None:
    entries = parse_manifest(read_outline(book_root))
    entry = resolve_target(entries)
    assert (entry.chapter_number, entry.pov) == (3, "ovist-rhoam")


def test_resolve_target_override_selects_existing_row(book_root: Path) -> None:
    entries = parse_manifest(read_outline(book_root))
    assert resolve_target(entries, override=2).pov == "brannec-tull"


def test_resolve_target_override_unknown_chapter(book_root: Path) -> None:
    entries = parse_manifest(read_outline(book_root))
    with pytest.raises(ConfigError, match="not in the manifest"):
        resolve_target(entries, override=99)


# --- flip_manifest_status ------------------------------------------------------


def read_outline(root: Path) -> str:
    return (root / "canon/plot-outline.md").read_text(encoding="utf-8")


def test_flip_changes_only_the_status_cell(book_root: Path) -> None:
    before = read_outline(book_root).splitlines()
    flip_manifest_status(book_root, 3, "written", expected_current="planned")
    after = read_outline(book_root).splitlines()

    assert len(before) == len(after)
    changed = [(o, n) for o, n in zip(before, after, strict=True) if o != n]
    assert len(changed) == 1
    old_cells = [c.strip() for c in changed[0][0].strip("|").split("|")]
    new_cells = [c.strip() for c in changed[0][1].strip("|").split("|")]
    assert old_cells[:2] == ["003", "ovist-rhoam"]
    # chapter, pov, arc unchanged; status changed; beat unchanged.
    assert [o == n for o, n in zip(old_cells, new_cells, strict=True)] == [
        True,
        True,
        True,
        False,
        True,
    ]
    assert new_cells[3] == "written"


def test_flip_then_parse_manifest_sees_written(book_root: Path) -> None:
    flip_manifest_status(book_root, 3, "written")
    entries = parse_manifest(read_outline(book_root))
    by_number = {e.chapter_number: e.status for e in entries}
    assert by_number[3] == "written"
    assert by_number[2] == "written"


def test_flip_refuses_wrong_expected_current(book_root: Path) -> None:
    with pytest.raises(VaultError, match="expected 'drafting'"):
        flip_manifest_status(book_root, 3, "written", expected_current="drafting")


def test_flip_refuses_illegal_status(book_root: Path) -> None:
    with pytest.raises(VaultError, match="Illegal manifest status"):
        flip_manifest_status(book_root, 3, "published")


def test_flip_refuses_unknown_chapter(book_root: Path) -> None:
    with pytest.raises(VaultError, match="no data row"):
        flip_manifest_status(book_root, 42, "written")


def test_flip_preserves_prose_outside_markers(book_root: Path) -> None:
    before = read_outline(book_root)
    pre_section = before.split("<!-- MANIFEST:BEGIN -->")[0]
    flip_manifest_status(book_root, 3, "written")
    after = read_outline(book_root)
    assert after.split("<!-- MANIFEST:BEGIN -->")[0] == pre_section
