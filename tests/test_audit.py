"""Audit layer tests: record shape matches specs §13, logs stay allowlisted."""

import logging

from novel_engine.core.config import ModelRoute
from novel_engine.providers.audit import CallRecord, CallRecorder
from novel_engine.providers.base import (
    RateLimited,
    Success,
    TransientFailure,
)

ROUTE = ModelRoute(provider="openrouter", model="model-a")


def success() -> Success:
    return Success(
        content="prose",
        model_id="served-model",
        input_tokens=10,
        output_tokens=5,
        latency_ms=100,
    )


def test_success_record_shape_matches_session_json() -> None:
    entry = CallRecord.capture(ROUTE, success(), 123)
    assert entry.model_dump(exclude={"at"}) == {
        "provider": "openrouter",
        "model_id": "served-model",  # what answered, not what was asked
        "outcome": "success",
        "latency_ms": 123,
        "input_tokens": 10,
        "output_tokens": 5,
        "status_code": None,
        "error": None,
    }


def test_failure_records_keep_route_model_and_error() -> None:
    failure = RateLimited(message="429 slow down", status_code=429)
    entry = CallRecord.capture(ROUTE, failure, 40)
    assert entry.model_id == "model-a"
    assert entry.outcome == "rate_limited"
    assert entry.status_code == 429
    assert "slow" in entry.error


def test_recorder_collects_and_shapes_audit_list() -> None:
    recorder = CallRecorder()
    recorder.record(ROUTE, TransientFailure(message="down", status_code=503), 9)
    recorder.record(ROUTE, success(), 100)
    calls = recorder.as_audit_list()
    assert [c["outcome"] for c in calls] == ["transient_failure", "success"]
    assert set(calls[0]) == {
        "provider",
        "model_id",
        "outcome",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "status_code",
        "error",
    }


def test_log_output_contains_only_allowlisted_fields(caplog) -> None:
    # Pitfall C4: a key smuggled into any non-allowlisted field must never
    # appear in log output.
    sneaky = Success(
        content="secret-body",
        model_id="m",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
    )
    recorder = CallRecorder()
    with caplog.at_level(logging.DEBUG):
        recorder.record(ROUTE, sneaky, 5)
        recorder.record(ROUTE, RateLimited(message="denied", status_code=429), 3)

    text = caplog.text
    assert "secret-body" not in text  # content is never logged
    assert "openrouter/model-a" in text.replace(" ", "")
    assert "rate_limited" in text
