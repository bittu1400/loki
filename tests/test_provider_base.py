"""Outcome taxonomy tests: fallback eligibility is the correctness core."""

from novel_engine.providers.base import (
    FALLBACK_ELIGIBLE,
    GenerationRequest,
    ModelUnavailable,
    PermanentFailure,
    RateLimited,
    Success,
    TransientFailure,
)


def test_success_is_ok() -> None:
    s = Success(
        content="prose", model_id="m", input_tokens=10, output_tokens=5, latency_ms=100
    )
    assert s.ok


def test_rate_limited_is_fallback_eligible() -> None:
    f = RateLimited(message="slow down", retry_after_seconds=30.0)
    assert isinstance(f, FALLBACK_ELIGIBLE)
    assert not f.ok
    assert f.retry_after_seconds == 30.0


def test_transient_failure_is_fallback_eligible() -> None:
    assert isinstance(TransientFailure(message="timeout"), FALLBACK_ELIGIBLE)


def test_model_unavailable_is_fallback_eligible() -> None:
    assert isinstance(ModelUnavailable(message="404 slug pulled"), FALLBACK_ELIGIBLE)


def test_permanent_failure_never_falls_back() -> None:
    # Pitfall C1: an auth error must not become a quota-burning retry storm.
    f = PermanentFailure(message="401 bad key", status_code=401)
    assert not f.fallback_eligible
    assert not isinstance(f, FALLBACK_ELIGIBLE)


def test_request_carries_no_secrets_and_defaults_match_pipeline() -> None:
    r = GenerationRequest(prompt="p", model_id="m")
    assert "key" not in r.__dataclass_fields__
    assert r.temperature == 0.9 and r.top_p == 0.95 and r.max_tokens == 4096
    assert r.json_mode is False
