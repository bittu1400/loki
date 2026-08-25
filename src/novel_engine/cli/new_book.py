"""Vault scaffolder: creates vault/<slug>/ from templates and exits
(ADR-0001 — a scaffolder, not an interview)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from novel_engine.core.errors import ConfigError
from novel_engine.core.vault import scaffold_book


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `new-book` console script."""
    parser = argparse.ArgumentParser(
        prog="new-book",
        description="Scaffold a blank book vault and exit.",
    )
    parser.add_argument("--slug", required=True, help="Book slug (kebab-case).")
    parser.add_argument(
        "--vault-root",
        type=Path,
        default=Path("vault"),
        help="Vault root directory (default: vault/).",
    )
    args = parser.parse_args(argv)

    try:
        root = scaffold_book(args.vault_root, args.slug)
    except ConfigError as exc:
        Console(stderr=True).print(f"[red]error[/red] {exc}")
        return 1

    created = sorted(
        str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
    )
    Console().print(f"[green]created[/green] {root} ({len(created)} files)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
