"""Session audit plumbing: structured call records + allowlist logging.

Redact by ALLOWLIST, never blocklist (pitfall C4): the logger emits only
fields it explicitly knows are safe. A key that lands in a new field is
silently omitted from logs by default — the failure mode is a missing log
line, not a leaked secret.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from pydantic import BaseModel

from novel_engine.core.config import ModelRoute
from novel_engine.providers.base import (
    ModelUnavailable,
    Outcome,
    PermanentFailure,
    RateLimited,
    Success,
    TransientFailure,
)

logger = logging.getLogger("novel-engine.providers")

#: The only fields ever emitted to logs. Everything else is dropped.
LOG_FIELDS = (
    "provider",
    "model_id",
    "outcome",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "status_code",
)

OUTCOME_NAMES: dict[type[Outcome], str] = {
    Success: "success",
    RateLimited: "rate_limited",
    TransientFailure: "transient_failure",
    ModelUnavailable: "model_unavailable",
    PermanentFailure: "permanent_failure",
}


def outcome_name(outcome: Outcome) -> str:
    return OUTCOME_NAMES[type(outcome)]


class CallRecord(BaseModel):
    """One attempted model call — the unit of the session JSON audit log."""

    provider: str
    model_id: str
    outcome: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    status_code: int | None = None
    error: str | None = None
    at: str = ""

    @classmethod
    def capture(
        cls, route: ModelRoute, outcome: Outcome, latency_ms: int
    ) -> CallRecord:
        success = isinstance(outcome, Success)
        return cls(
            provider=route.provider,
            # Record what actually answered, not just what was requested —
            # when a chapter's voice is off, this is the first question.
            model_id=outcome.model_id if success else route.model,
            outcome=outcome_name(outcome),
            latency_ms=latency_ms,
            input_tokens=outcome.input_tokens if success else 0,
            output_tokens=outcome.output_tokens if success else 0,
            status_code=getattr(outcome, "status_code", None),
            error=None if success else outcome.message[:500],
            at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        )


class CallRecorder:
    """Collects CallRecords; pass its .record method as the Router's
    on_attempt callback so every attempt lands in the session audit."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def record(self, route: ModelRoute, outcome: Outcome, latency_ms: int) -> None:
        entry = CallRecord.capture(route, outcome, latency_ms)
        self.records.append(entry)
        _log_safe(entry)

    def as_audit_list(self) -> list[dict[str, Any]]:
        """Shape matching specs.md §13 session JSONs' `calls` array."""
        return [record.model_dump(exclude={"at"}) for record in self.records]


def _log_safe(entry: CallRecord) -> None:
    data = entry.model_dump(include=set(LOG_FIELDS))
    suffix = f" [{data['status_code']}]" if data["status_code"] is not None else ""
    level = logging.INFO if entry.outcome == "success" else logging.WARNING
    logger.log(
        level,
        "%s/%s -> %s (%d ms, in=%d out=%d)%s",
        data["provider"],
        data["model_id"],
        data["outcome"],
        data["latency_ms"],
        data["input_tokens"],
        data["output_tokens"],
        suffix,
    )
