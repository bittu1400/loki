"""Smoke test: the package imports and entry points resolve."""

import pytest


def test_package_imports() -> None:
    import novel_engine

    assert novel_engine.__doc__ is not None


@pytest.mark.parametrize(
    ("module", "attr"),
    [
        ("novel_engine.cli.new_book", "main"),
        ("novel_engine.cli.write_session", "main"),
        ("novel_engine.cli.check_style", "main"),
    ],
)
def test_console_entry_points_resolve(module: str, attr: str) -> None:
    import importlib

    assert hasattr(importlib.import_module(module), attr)
