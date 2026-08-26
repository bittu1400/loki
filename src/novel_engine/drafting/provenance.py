"""Chapter frontmatter construction: provenance, model, prompt hash.

Every field here answers a question someone will ask later: which model
was SUPPOSED to write this, which one DID, did fallback fire, how many
continuation rounds were burned. Flat scalars only — Notion compatibility
(specs.md §1).
"""

from __future__ import annotations

import datetime as dt
import re
import secrets

SESSION_ID_PATTERN = re.compile(r"^sess-\d{8}-\d{4}-[0-9a-f]{4}$")


def make_session_id(now: dt.datetime | None = None) -> str:
    """`sess-YYYYMMDD-HHMM-<4 hex>` — unique per invocation (specs.md §11)."""
    moment = now or dt.datetime.now(dt.UTC)
    return f"sess-{moment:%Y%m%d-%H%M}-{secrets.token_hex(2)}"


def chapter_frontmatter(
    *,
    chapter_number: int,
    book_slug: str,
    pov: str,
    arc: str,
    status: str,
    session_id: str,
    created_at: str,
    target_words: int,
    actual_words: int,
    assigned_model: str,
    actual_model: str,
    fallback_triggered: bool,
    continuation_rounds: int,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, object]:
    """The flat frontmatter dict for chapters/chapter-NNN.md (specs §3).

    `generated_hash` is deliberately absent: the writing primitive in
    core/vault.py computes and owns it from the body as generated.
    """
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(
            f"session id {session_id!r} does not match sess-YYYYMMDD-HHMM-xxxx"
        )
    return {
        "chapter_number": chapter_number,
        "book_slug": book_slug,
        "pov": pov,
        "arc": arc,
        "status": status,
        "session_id": session_id,
        "created_at": created_at,
        "target_words": target_words,
        "actual_words": actual_words,
        "assigned_model": assigned_model,
        "actual_model": actual_model,
        "fallback_triggered": fallback_triggered,
        "continuation_rounds": continuation_rounds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def utc_timestamp(now: dt.datetime | None = None) -> str:
    moment = now or dt.datetime.now(dt.UTC)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")
