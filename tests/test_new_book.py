"""Scaffolder tests: vault.py scaffold_book + cli.new_book main."""

from pathlib import Path

import pytest

from novel_engine.core.config import load_book_config
from novel_engine.core.errors import ConfigError
from novel_engine.core.vault import scaffold_book

FAKE_ENV = {
    "GEMINI_API_KEY": "test-gemini",
    "OPENROUTER_API_KEY": "test-openrouter",
    "GROQ_API_KEY": "test-groq",
    # The scaffolder's editor_model fallback routes mistral (verified
    # 2026-09-01). A scaffolded book that names a provider must demand
    # that provider's key at startup — that demand IS the behaviour
    # under test here.
    "MISTRAL_API_KEY": "test-mistral",
}


def test_scaffold_creates_valid_tree(tmp_path: Path) -> None:
    root = scaffold_book(tmp_path, "test-book")
    assert (root / "config/models.yaml").is_file()
    assert (root / "canon/continuity-tracker.md").is_file()
    assert "<!-- FACTS:BEGIN -->" in (root / "canon/continuity-tracker.md").read_text()
    assert "<!-- MANIFEST:BEGIN -->" in (root / "canon/plot-outline.md").read_text()


def test_scaffolded_book_passes_validation(tmp_path: Path) -> None:
    scaffold_book(tmp_path, "test-book")
    config = load_book_config(tmp_path, "test-book", env=FAKE_ENV)
    assert config.slug == "test-book"
    assert config.manifest == []


def test_scaffold_refuses_overwrite(tmp_path: Path) -> None:
    scaffold_book(tmp_path, "test-book")
    sentinel = tmp_path / "test-book/canon/story-bible.md"
    sentinel.write_text("author content\n")
    with pytest.raises(ConfigError, match="Refusing to overwrite"):
        scaffold_book(tmp_path, "test-book")
    assert sentinel.read_text() == "author content\n"


def test_scaffold_rejects_bad_slug(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid"):
        scaffold_book(tmp_path, "Test_Book")


def test_cli_main_creates_and_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from novel_engine.cli.new_book import main

    assert main(["--slug", "cli-book", "--vault-root", str(tmp_path)]) == 0
    assert (tmp_path / "cli-book/config/pipeline.yaml").is_file()

    # Second run fails with exit code 1 and an actionable message.
    assert main(["--slug", "cli-book", "--vault-root", str(tmp_path)]) == 1
    assert "Refusing to overwrite" in capsys.readouterr().err
