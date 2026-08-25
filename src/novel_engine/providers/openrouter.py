"""OpenRouter route constants and constructor."""

from __future__ import annotations

import httpx

from novel_engine.providers.openai_compat import OpenAICompatProvider

NAME = "openrouter"
BASE_URL = "https://openrouter.ai/api/v1"


def build(
    api_key: str,
    *,
    site_url: str | None = None,
    app_name: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> OpenAICompatProvider:
    """Optional Site URL / App Name headers affect free-tier ranking
    (OPENROUTER_SITE_URL / OPENROUTER_APP_NAME)."""
    extra: dict[str, str] = {}
    if site_url:
        extra["HTTP-Referer"] = site_url
    if app_name:
        extra["X-Title"] = app_name
    return OpenAICompatProvider(
        NAME, BASE_URL, api_key, extra_headers=extra, transport=transport
    )
