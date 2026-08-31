"""Local llama.cpp lane (ADR-0006) — last resort, never rate-limited.

Speaks the same OpenAI-compatible wire format as the hosted lanes, with
two differences that matter:

- **No API key.** The server does not authenticate, so no Authorization
  header is sent.
- **A hard context window.** A hosted lane's limit is generous and
  invisible; this one is whatever the server was started with, and
  exceeding it fails the call rather than truncating politely. The
  provider clamps `max_tokens` so prompt + output fit, and refuses the
  call outright when the prompt alone leaves no room to write.

The lane is dead whenever the server is not running. That is classified
as ModelUnavailable, not TransientFailure: retrying in place will not
start a server, but a different provider can still answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from novel_engine.providers.base import (
    GenerationRequest,
    ModelUnavailable,
    Outcome,
)
from novel_engine.providers.openai_compat import OpenAICompatProvider

NAME = "local"
DEFAULT_BASE_URL = "http://localhost:8080/v1"

#: The server's context window. A physical property of how llama.cpp was
#: started, not a creative setting — override with LOCAL_CONTEXT_WINDOW
#: when the server is launched with a different -c.
DEFAULT_CONTEXT_WINDOW = 8192

#: Leave room for the chat template's own wrapper tokens and for the
#: chars-per-token estimate being optimistic on punctuation-dense prose.
CONTEXT_MARGIN_TOKENS = 256

#: Below this there is no point calling: the model cannot write a scene.
MIN_OUTPUT_TOKENS = 512

#: Rough tokens-per-character for English prose. Deliberately pessimistic
#: (real ratio is nearer 4.0) so the clamp errs toward fitting.
CHARS_PER_TOKEN = 3.5


class LocalProvider(OpenAICompatProvider):
    """OpenAI-compatible provider with a context ceiling and no auth."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(NAME, base_url, api_key=None, transport=transport)
        self.context_window = context_window

    def estimate_prompt_tokens(self, prompt: str) -> int:
        return int(len(prompt) / CHARS_PER_TOKEN) + 1

    def room_for_output(self, prompt: str) -> int:
        """Output tokens that still fit after the prompt. May be <= 0."""
        return (
            self.context_window
            - self.estimate_prompt_tokens(prompt)
            - CONTEXT_MARGIN_TOKENS
        )

    def build_payload(self, request: GenerationRequest) -> dict[str, Any]:
        payload = super().build_payload(request)
        payload["max_tokens"] = min(
            request.max_tokens, self.room_for_output(request.prompt)
        )
        return payload

    def generate(self, request: GenerationRequest) -> Outcome:
        room = self.room_for_output(request.prompt)
        if room < MIN_OUTPUT_TOKENS:
            # Sending this would either error or return a stub. Say so
            # honestly and let the chain move on.
            return ModelUnavailable(
                message=(
                    f"prompt needs ~{self.estimate_prompt_tokens(request.prompt)} "
                    f"tokens of a {self.context_window}-token window, leaving "
                    f"{room} for output (minimum {MIN_OUTPUT_TOKENS}). Restart "
                    "the server with a larger -c, or shrink the context."
                )
            )
        return super().generate(request)


def build(
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> LocalProvider:
    """Build the local lane, honouring LOCAL_BASE_URL / LOCAL_CONTEXT_WINDOW."""
    env = env or {}
    window = env.get("LOCAL_CONTEXT_WINDOW", "").strip()
    return LocalProvider(
        env.get("LOCAL_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        context_window=int(window) if window.isdigit() else DEFAULT_CONTEXT_WINDOW,
        transport=transport,
    )
