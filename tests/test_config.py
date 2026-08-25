"""Config loader tests against vault/example-book/ plus seeded failures."""

import shutil
from pathlib import Path

import pytest

from novel_engine.core.config import load_book_config
from novel_engine.core.errors import ConfigError
from novel_engine.core.outline import ManifestError, next_target, parse_manifest

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"
FAKE_ENV = {
    "GEMINI_API_KEY": "test-gemini",
    "OPENROUTER_API_KEY": "test-openrouter",
    "GROQ_API_KEY": "test-groq",
}


@pytest.fixture
def book(tmp_path: Path) -> Path:
    copied = tmp_path / "example-book"
    shutil.copytree(FIXTURE, copied)
    return copied


def test_fixture_loads_cleanly() -> None:
    config = load_book_config(FIXTURE.parent, "example-book", env=FAKE_ENV)
    assert config.slug == "example-book"
    assert set(config.characters) == {"ovist-rhoam", "brannec-tull", "sela-vosk"}
    assert [entry.chapter_number for entry in config.manifest] == [1, 2, 3, 4]


def test_missing_book_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="new-book --slug ghost-book"):
        load_book_config(tmp_path, "ghost-book", env=FAKE_ENV)


def test_invalid_slug(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid"):
        load_book_config(tmp_path, "Not_A_Slug", env=FAKE_ENV)


def test_path_traversal_refused(tmp_path: Path) -> None:
    # A valid-looking slug that symlinks outside the vault must still be
    # refused by the containment check.
    outside = tmp_path / "outside"
    outside.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "sneaky").symlink_to(outside)
    with pytest.raises(ConfigError, match="vault root"):
        load_book_config(vault, "sneaky", env=FAKE_ENV)


def test_missing_required_file(book: Path) -> None:
    (book / "canon/story-bible.md").unlink()
    with pytest.raises(ConfigError, match=r"story-bible\.md"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


def test_non_kebab_filename_rejected(book: Path) -> None:
    (book / "canon/story_bible.md").write_text("bad name\n")
    with pytest.raises(ConfigError, match="kebab-case"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


def test_unknown_provider_rejected(book: Path) -> None:
    models = book / "config/models.yaml"
    models.write_text(models.read_text().replace("groq", "anthropic"))
    with pytest.raises(ConfigError, match="unknown provider"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


def test_empty_model_id_rejected(book: Path) -> None:
    models = book / "config/models.yaml"
    models.write_text(
        models.read_text().replace("model: gemini-2.5-flash", 'model: ""', 1)
    )
    with pytest.raises(ConfigError, match="model ID is empty"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


@pytest.mark.parametrize(
    ("var", "provider"),
    [
        ("GEMINI_API_KEY", "gemini"),
        ("OPENROUTER_API_KEY", "openrouter"),
        ("GROQ_API_KEY", "groq"),
    ],
)
def test_missing_env_var_fails_fast(book: Path, var: str, provider: str) -> None:
    env = {key: value for key, value in FAKE_ENV.items() if key != var}
    with pytest.raises(ConfigError, match=var):
        load_book_config(book.parent, "example-book", env=env)
    del provider  # parametrised for readable failure output only


def test_manifest_pov_not_in_index(book: Path) -> None:
    outline = book / "canon/plot-outline.md"
    text = outline.read_text().replace("| 003 | ovist-rhoam |", "| 003 | nobody-here |")
    outline.write_text(text)
    with pytest.raises(ConfigError, match="nobody-here"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


def test_pov_character_without_route(book: Path) -> None:
    index = book / "characters/index.yaml"
    text = index.read_text()
    index.write_text(text.replace("pov: false", "pov: true"))
    with pytest.raises(ConfigError, match="sela-vosk"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


def test_index_points_at_missing_file(book: Path) -> None:
    (book / "characters/sela-vosk.md").unlink()
    with pytest.raises(ConfigError, match=r"sela-vosk\.md"):
        load_book_config(book.parent, "example-book", env=FAKE_ENV)


MANIFEST = """\
# Plot Outline

<!-- MANIFEST:BEGIN -->
| chapter | pov | arc | status | beat |
|---------|-----|-----|--------|------|
| 001 | a | arc-1 | written | One. |
| 002 | b | arc-1 | planned | Two. |
<!-- MANIFEST:END -->
"""


def test_parse_manifest_happy_path() -> None:
    entries = parse_manifest(MANIFEST)
    assert [entry.chapter_number for entry in entries] == [1, 2]
    assert next_target(entries) == 2


def test_parse_manifest_ignores_prose() -> None:
    prose = MANIFEST.replace(
        "<!-- MANIFEST:BEGIN -->",
        "## Act I — free prose mentioning chapter | 099 |\n\n<!-- MANIFEST:BEGIN -->",
    )
    entries = parse_manifest(prose)
    assert len(entries) == 2


def test_parse_manifest_missing_markers() -> None:
    with pytest.raises(ManifestError, match="exactly one"):
        parse_manifest("# no markers here")


def test_parse_manifest_missing_column() -> None:
    bad = MANIFEST.replace("| pov ", "| ")
    with pytest.raises(ManifestError, match="pov"):
        parse_manifest(bad)


def test_parse_manifest_illegal_status() -> None:
    bad = MANIFEST.replace("written", "finished")
    with pytest.raises(ManifestError, match="finished"):
        parse_manifest(bad)


def test_parse_manifest_duplicate_chapter() -> None:
    bad = MANIFEST.replace("| 002 |", "| 001 |")
    with pytest.raises(ManifestError, match="Duplicate"):
        parse_manifest(bad)


def test_next_target_gap_aborts() -> None:
    gapped = MANIFEST.replace("| 002 |", "| 004 |")
    entries = parse_manifest(gapped)
    with pytest.raises(ConfigError, match="non-contiguous"):
        next_target(entries)
