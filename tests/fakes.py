"""Shared test doubles: scripted providers sized for the shrunk pipeline."""

from novel_engine.providers.base import (
    GenerationRequest,
    Outcome,
    Provider,
    RateLimited,
)


class FakeProvider(Provider):
    """Serves a scripted list of outcomes, repeating the last one."""

    name = "fake"

    def __init__(self, *outcomes: Outcome):
        self.script = list(outcomes)
        # Repeat the final scripted outcome once the script runs dry.
        self._default = self.script[-1] if self.script else RateLimited("exhausted")
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> Outcome:
        self.calls.append(request)
        if self.script:
            return self.script.pop(0)
        return self._default

    def serve(self, *outcomes: Outcome, default: Outcome) -> None:
        self.script = list(outcomes)
        self._default = default


def full_providers(**named: FakeProvider) -> dict[str, FakeProvider]:
    """Every provider the fixture routes mention; unrouted ones never fire
    (the Router validates the whole chain up front)."""
    providers = {
        name: FakeProvider(RateLimited("unused"))
        for name in ("openrouter", "nvidia", "groq")
    }
    providers.update(named)
    return providers


def text_of(words: int, seed: str = "w") -> str:
    return " ".join(f"{seed}{i}" for i in range(words))
