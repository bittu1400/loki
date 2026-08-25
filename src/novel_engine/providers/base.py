"""Abstract provider and normalised outcome types.

Five outcomes as distinct types — a correctness requirement, not style
(pitfall C1): success · rate-limited · transient · permanent ·
model-unavailable. Only the first three failure kinds are fallback-
eligible; PermanentFailure is not, so the router cannot fall back on an
auth error or malformed prompt even by accident.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationRequest:
    """Everything a provider needs for one call. No secrets inside."""

    prompt: str
    model_id: str
    max_tokens: int = 4096
    temperature: float = 0.9
    top_p: float = 0.95
    json_mode: bool = False


@dataclass(frozen=True)
class Success:
    content: str
    model_id: str  # what actually answered; may differ from what was asked
    input_tokens: int
    output_tokens: int
    latency_ms: int

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class _Failure:
    """Base for failures. Subclasses declare fallback eligibility."""

    message: str
    status_code: int | None = None
    retry_after_seconds: float | None = None

    @property
    def ok(self) -> bool:
        return False

    @property
    def fallback_eligible(self) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class RateLimited(_Failure):
    """429 from us or upstream. Fallback-eligible."""

    @property
    def fallback_eligible(self) -> bool:
        return True


@dataclass(frozen=True)
class TransientFailure(_Failure):
    """Timeouts, connection errors, 5xx. Fallback-eligible."""

    @property
    def fallback_eligible(self) -> bool:
        return True


@dataclass(frozen=True)
class ModelUnavailable(_Failure):
    """404 / pulled slug / gated route. Fallback-eligible."""

    @property
    def fallback_eligible(self) -> bool:
        return True


@dataclass(frozen=True)
class PermanentFailure(_Failure):
    """Auth errors, paywalls, blocked routes, malformed requests.

    NOT fallback-eligible (pitfall C1): retrying across providers burns
    quota on a deterministic bug.
    """

    @property
    def fallback_eligible(self) -> bool:
        return False


Outcome = Success | RateLimited | TransientFailure | ModelUnavailable | PermanentFailure

#: Outcomes that may move to the next route in the chain.
FALLBACK_ELIGIBLE = (RateLimited, TransientFailure, ModelUnavailable)


class Provider(ABC):
    """A stateless worker that turns a GenerationRequest into an Outcome.

    Providers know nothing about novels — no beats, no continuity, no
    frontmatter (best-practices §1 layering rule).
    """

    #: Short key matching KNOWN_PROVIDERS in core.config.
    name: str

    @abstractmethod
    def generate(self, request: GenerationRequest) -> Outcome:
        """Make one API call. Must never raise for expected API failures —
        those are Outcomes. Raise only for programming errors."""
