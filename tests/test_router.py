"""Router tests: fallback order, retry counts, permanent-failure abort.

Fake providers record every call so the quota-burning failure modes
(pitfall C1) are asserted against directly, not inferred.
"""

import random

from novel_engine.core.config import GenerationParams, ModelRoute, RetryConfig
from novel_engine.providers.base import (
    GenerationRequest,
    ModelUnavailable,
    Outcome,
    PermanentFailure,
    Provider,
    RateLimited,
    Success,
    TransientFailure,
)
from novel_engine.providers.router import Router

PRIMARY = ModelRoute(provider="openrouter", model="model-a")
SECONDARY = ModelRoute(provider="groq", model="model-b")


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, outcomes: list[Outcome]) -> None:
        assert outcomes, "FakeProvider needs at least one scripted outcome."
        self._outcomes = list(outcomes)
        self._last = self._outcomes[-1]
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> Outcome:
        self.calls.append(request)
        if self._outcomes:
            return self._outcomes.pop(0)
        # Sticky: an exhausted script repeats its final outcome, so tests
        # can assert on the last real failure rather than harness noise.
        return self._last


def ok(content: str = "prose") -> Success:
    return Success(
        content=content, model_id="m", input_tokens=1, output_tokens=1, latency_ms=1
    )


NO_WAIT = RetryConfig(
    max_attempts=3, base_delay_seconds=0.0, jitter=False, respect_retry_after=True
)


class Recorder:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def build_router(
    providers: dict[str, FakeProvider],
    routes: list[ModelRoute],
    retry: RetryConfig | None = None,
    **kwargs,
) -> tuple[Router, Recorder]:
    recorder = Recorder()
    router = Router(
        providers=providers,  # type: ignore[arg-type]
        routes=routes,
        retry=retry or NO_WAIT,
        generation_params=GenerationParams(),
        sleeper=recorder.sleep,
        rng=random.Random(7),
        **kwargs,
    )
    return router, recorder


def test_primary_success_makes_exactly_one_call() -> None:
    providers = {"openrouter": FakeProvider([ok()])}
    router, _ = build_router(providers, [PRIMARY])
    outcome = router.generate("prompt")
    assert isinstance(outcome, Success)
    assert len(providers["openrouter"].calls) == 1
    assert providers["openrouter"].calls[0].model_id == "model-a"


def test_rate_limit_retries_same_route_then_succeeds() -> None:
    provider = FakeProvider([RateLimited(message="429"), ok("second try")])
    router, _ = build_router({"openrouter": provider}, [PRIMARY])
    outcome = router.generate("p")
    assert isinstance(outcome, Success)
    assert outcome.content == "second try"
    assert len(provider.calls) == 2


def test_permanent_failure_aborts_chain_immediately() -> None:
    secondary = FakeProvider([ok()])
    router, _ = build_router(
        {
            "openrouter": FakeProvider([PermanentFailure(message="401")]),
            "groq": secondary,
        },
        [PRIMARY, SECONDARY],
    )
    outcome = router.generate("p")
    assert isinstance(outcome, PermanentFailure)
    assert secondary.calls == []  # pitfall C1: no quota burned downstream


def test_model_unavailable_moves_to_next_route_without_retry() -> None:
    primary = FakeProvider([ModelUnavailable(message="404 slug pulled")])
    secondary = FakeProvider([ok()])
    router, _ = build_router(
        {"openrouter": primary, "groq": secondary}, [PRIMARY, SECONDARY]
    )
    outcome = router.generate("p")
    assert isinstance(outcome, Success)
    assert len(primary.calls) == 1  # no pointless retries of a dead slug


def test_all_routes_fail_returns_last_failure() -> None:
    router, _ = build_router(
        {
            "openrouter": FakeProvider([TransientFailure(message="down")]),
            "groq": FakeProvider([RateLimited(message="429")]),
        },
        [PRIMARY, SECONDARY],
    )
    outcome = router.generate("p")
    assert isinstance(outcome, RateLimited)


def test_backoff_respects_retry_after_header() -> None:
    provider = FakeProvider([RateLimited(message="429", retry_after_seconds=7.5), ok()])
    router, recorder = build_router({"openrouter": provider}, [PRIMARY])
    assert isinstance(router.generate("p"), Success)
    # The single wait honours Retry-After exactly; no jitter added to it.
    assert recorder.sleeps == [7.5]


def test_backoff_doubles_without_retry_after() -> None:
    provider = FakeProvider(
        [RateLimited(message="429"), RateLimited(message="429"), ok()]
    )
    retry = RetryConfig(max_attempts=3, base_delay_seconds=1.0, jitter=False)
    router, recorder = build_router({"openrouter": provider}, [PRIMARY], retry=retry)
    assert isinstance(router.generate("p"), Success)
    assert recorder.sleeps == [1.0, 2.0]


def test_on_attempt_callback_sees_every_call() -> None:
    seen: list[tuple[str, str]] = []
    provider = FakeProvider([RateLimited(message="429"), ok()])
    router, _ = build_router(
        {"openrouter": provider},
        [PRIMARY],
        on_attempt=lambda route, outcome, ms: seen.append(
            (route.model, type(outcome).__name__)
        ),
    )
    router.generate("p")
    assert seen == [("model-a", "RateLimited"), ("model-a", "Success")]
