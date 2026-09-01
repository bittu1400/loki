"""Project exception hierarchy (best-practices.md §1).

Every module raises from here, never bare `Exception`. Implemented as
phases need them.
"""

from __future__ import annotations


class NovelEngineError(Exception):
    """Base class for every error this project raises."""


class ContextError(NovelEngineError):
    """A vault file the context builder reads is malformed or incomplete.

    Raised before any API call. Messages name the file, the offending
    line, and what would fix it — reading canon fails loudly rather than
    prompting a model with silently wrong context.
    """


class VaultError(NovelEngineError):
    """A vault write was refused or the vault changed under us.

    Raised by core/vault.py primitives: overwrite refusal, manifest
    status flips that do not match expectations, or a write whose
    verification failed. Nothing is half-written when this fires.
    """


class ConfigError(NovelEngineError):
    """Configuration is missing, malformed, or inconsistent.

    Raised at startup, before any API call. Messages are actionable:
    they name the file, the offending value, and what would fix it.
    """


class EditorialError(NovelEngineError):
    """The editorial model's delta is not usable.

    Malformed JSON, a schema violation, or a field that could not be
    turned into a canon line. Raised before anything is written, and
    never fallback-eligible: a schema failure is a PERMANENT failure
    (specs.md §12) and must not walk the drafting fallback chain
    (invariant 3).
    """
