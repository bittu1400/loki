"""NVIDIA NIM route constants and constructor."""

from __future__ import annotations

import httpx

from novel_engine.providers.openai_compat import OpenAICompatProvider

NAME = "nvidia"
BASE_URL = "https://integrate.api.nvidia.com/v1"


def build(
    api_key: str, *, transport: httpx.BaseTransport | None = None
) -> OpenAICompatProvider:
    return OpenAICompatProvider(NAME, BASE_URL, api_key, transport=transport)
