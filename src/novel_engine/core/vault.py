"""Markdown and frontmatter IO; safe append primitives.

THE ONE-WRITER RULE: this is the only module in the project permitted to
write to disk. Everything else returns data. Exposes append primitives
only — append_fact, append_summary, append_thread, flip_thread_status —
and deliberately no general "write canon file" function (invariant 1).
"""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from novel_engine.core.config import SLUG_PATTERN
from novel_engine.core.errors import ConfigError


def scaffold_book(vault_root: Path | str, slug: str) -> Path:
    """Create vault/<slug>/ from the packaged templates and return its root.

    A scaffolder, not an interview (ADR-0001). Refuses to overwrite an
    existing book directory.
    """
    if not SLUG_PATTERN.fullmatch(slug):
        raise ConfigError(
            f"Book slug {slug!r} is not valid. Use lowercase letters, digits, "
            "and hyphens (e.g. 'the-salt-almanac')."
        )

    vault = Path(vault_root).resolve()
    root = (vault / slug).resolve()
    if root.parent != vault:
        raise ConfigError(
            f"Book path {root} does not resolve directly under {vault}; "
            "refusing to write outside the vault root."
        )
    if root.exists():
        raise ConfigError(
            f"Refusing to overwrite existing book directory: {root}. "
            "Pick another slug or remove the directory yourself."
        )

    templates = resources.files("novel_engine") / "templates" / "book"
    with resources.as_file(templates) as source:
        shutil.copytree(source, root)

    return root
