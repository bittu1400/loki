"""check-style CLI: measures without keys, exits 0 on out-of-band metrics
(they are advisory, specs §14), and 1 only on real errors."""

import shutil
from pathlib import Path

from rich.console import Console

from novel_engine.cli.check_style import check_style, main

FIXTURE = Path(__file__).resolve().parents[1] / "vault" / "example-book"


def copy_vault(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    shutil.copytree(FIXTURE, vault_root / "example-book")
    return vault_root


def run(vault_root: Path, chapter: int) -> tuple[int, str]:
    console = Console(record=True, width=100, no_color=True)
    code = check_style("example-book", chapter, vault_root, console=console)
    return code, console.export_text()


def test_out_of_band_metrics_still_exit_zero(tmp_path):
    code, output = run(copy_vault(tmp_path), 4)
    assert code == 0
    assert "outside band" in output
    assert "dialogue_ratio" in output


def test_clean_chapter_reports_thresholds_met(tmp_path):
    code, output = run(copy_vault(tmp_path), 1)
    assert code == 0
    assert "every declared threshold met" in output


def test_missing_thresholds_block_is_reported_not_failed(tmp_path):
    vault_root = copy_vault(tmp_path)
    guide = vault_root / "example-book" / "canon" / "style-guide.md"
    text = guide.read_text(encoding="utf-8")
    guide.write_text(text[: text.index("<!-- THRESHOLDS:BEGIN -->")], encoding="utf-8")

    code, output = run(vault_root, 3)
    assert code == 0
    assert "verdicts skipped" in output


def test_banned_phrase_hits_are_listed(tmp_path):
    vault_root = copy_vault(tmp_path)
    chapter = vault_root / "example-book" / "chapters" / "chapter-001.md"
    text = chapter.read_text(encoding="utf-8")
    chapter.write_text(text + "\n\nThe air was thick with salt.\n", encoding="utf-8")

    code, output = run(vault_root, 1)
    assert code == 0
    assert "banned phrases" in output
    assert "the air was thick with" in output


def test_missing_chapter_exits_one(tmp_path, capsys):
    vault_root = copy_vault(tmp_path)
    argv = ["--book", "example-book", "--chapter", "99"]
    argv += ["--vault-root", str(vault_root)]
    assert main(argv) == 1
    assert "does not exist" in capsys.readouterr().err


def test_malformed_thresholds_exit_one(tmp_path, capsys):
    vault_root = copy_vault(tmp_path)
    guide = vault_root / "example-book" / "canon" / "style-guide.md"
    guide.write_text(
        guide.read_text(encoding="utf-8").replace(
            "| dialogue_ratio | - | 0.35 |", "| dialogue_ratio | - | loose |"
        ),
        encoding="utf-8",
    )

    argv = ["--book", "example-book", "--chapter", "1"]
    argv += ["--vault-root", str(vault_root)]
    assert main(argv) == 1
    assert "non-numeric" in capsys.readouterr().err


def test_runs_with_no_api_keys_in_the_environment(tmp_path, monkeypatch):
    for key in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    assert run(copy_vault(tmp_path), 2)[0] == 0
