"""Fallback chain and backoff with jitter.

Permanent failures never trigger fallback (invariant 3): the router
returns immediately without touching another provider. Rate-limited and
transient outcomes are retried on the same route up to the configured
attempts before moving down the chain; a pulled model moves on at once.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping, Sequence

from novel_engine.core.config import GenerationParams, ModelRoute, RetryConfig
from novel_engine.providers.base import (
    GenerationRequest,
    Outcome,
    Provider,
    RateLimited,
    Success,
)

#: Called after every attempt with (route, outcome, latency_ms). The audit
#: layer (Phase 2 Batch 4) subscribes here; nothing logs by default.
AttemptCallback = Callable[[ModelRoute, Outcome, int], None]


class Router:
    """Walks an ordered route list, applying per-route retries."""

    def __init__(
        self,
        providers: Mapping[str, Provider],
        routes: Sequence[ModelRoute],
        retry: RetryConfig,
        generation_params: GenerationParams | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        on_attempt: AttemptCallback | None = None,
    ) -> None:
        if not routes:
            raise ValueError("Router needs at least one route.")
        missing = sorted({r.provider for r in routes if r.provider not in providers})
        if missing:
            raise ValueError(f"No provider instance for: {', '.join(missing)}")
        self._providers = providers
        self._routes = list(routes)
        self._retry = retry
        self._params = generation_params or GenerationParams()
        self._sleep = sleeper
        self._rng = rng or random.Random()
        self._on_attempt = on_attempt

    def _delay(self, attempt: int, outcome: Outcome) -> float:
        if (
            isinstance(outcome, RateLimited)
            and outcome.retry_after_seconds is not None
            and self._retry.respect_retry_after
        ):
            return outcome.retry_after_seconds
        delay = self._retry.base_delay_seconds * (2**attempt)
        if self._retry.jitter:
            delay += self._rng.uniform(0, 1)
        return delay

    def generate(self, prompt: str, *, json_mode: bool = False) -> Outcome:
        """Try each route in order; return the first Success or the last
        failure. A PermanentFailure short-circuits the whole chain.

        Retry policy: only RateLimited outcomes retry on the same route —
        the server told us when to come back. Transient failures and
        unavailable models move down the chain at once; waiting on a
        timing-out endpoint wastes session time, and a pulled slug will
        not return mid-session.
        """
        last_failure: Outcome | None = None
        for route in self._routes:
            request = GenerationRequest(
                prompt=prompt,
                model_id=route.model,
                max_tokens=4096,
                temperature=self._params.temperature,
                top_p=self._params.top_p,
                json_mode=json_mode,
            )
            for attempt in range(self._retry.max_attempts):
                started = time.monotonic()
                outcome = self._providers[route.provider].generate(request)
                latency_ms = int((time.monotonic() - started) * 1000)
                if self._on_attempt is not None:
                    self._on_attempt(route, outcome, latency_ms)

                if isinstance(outcome, Success):
                    return outcome
                if not outcome.fallback_eligible:
                    # Pitfall C1: deterministic bug — stop everything now.
                    return outcome
                last_failure = outcome

                if (
                    isinstance(outcome, RateLimited)
                    and attempt + 1 < self._retry.max_attempts
                ):
                    self._sleep(self._delay(attempt, outcome))
                    continue
                break  # anything else: let the next route have its turn
        assert last_failure is not None  # routes non-empty; something failed
        return last_failure
