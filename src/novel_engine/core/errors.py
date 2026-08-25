"""Project exception hierarchy (best-practices.md §1).

Every module raises from here, never bare `Exception`. Implemented as
phases need them.
"""

from __future__ import annotations


class NovelEngineError(Exception):
    """Base class for every error this project raises."""


class ConfigError(NovelEngineError):
    """Configuration is missing, malformed, or inconsistent.

    Raised at startup, before any API call. Messages are actionable:
    they name the file, the offending value, and what would fix it.
    """
