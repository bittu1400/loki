"""Mistral La Plateforme route constants and constructor."""

from __future__ import annotations

import httpx

from novel_engine.providers.openai_compat import OpenAICompatProvider

NAME = "mistral"
BASE_URL = "https://api.mistral.ai/v1"


def build(
    api_key: str, *, transport: httpx.BaseTransport | None = None
) -> OpenAICompatProvider:
    return OpenAICompatProvider(NAME, BASE_URL, api_key, transport=transport)
