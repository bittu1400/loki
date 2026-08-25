"""AiHubMix route constants and constructor.

Aggregator speaking the OpenAI wire format; carries `:free`-suffixed
models (notably minimax-m3-free) on an independent quota from
OpenRouter/NVIDIA, giving the same model a third free lane.
"""

from __future__ import annotations

import httpx

from novel_engine.providers.openai_compat import OpenAICompatProvider

NAME = "aihubmix"
BASE_URL = "https://aihubmix.com/v1"


def build(
    api_key: str, *, transport: httpx.BaseTransport | None = None
) -> OpenAICompatProvider:
    return OpenAICompatProvider(NAME, BASE_URL, api_key, transport=transport)
