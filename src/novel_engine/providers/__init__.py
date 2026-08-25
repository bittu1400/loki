"""Provider package. Knows nothing about novels.

`build_providers(env)` constructs every provider whose key is present in
the environment mapping. Providers with missing keys are simply absent —
startup validation (core.config) already guarantees the routes a book
needs are all satisfiable before any call is made.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from novel_engine.providers import (
    aihubmix,
    gemini,
    groq,
    mistral,
    nvidia,
    openrouter,
)
from novel_engine.providers.base import Provider

#: provider name -> env var holding its key.
ENV_KEYS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "aihubmix": "AIHUBMIX_API_KEY",
}


def build_providers(
    env: Mapping[str, str], *, transport: httpx.BaseTransport | None = None
) -> dict[str, Provider]:
    """Build every provider with a non-empty key present."""
    providers: dict[str, Provider] = {}
    for name, var in ENV_KEYS.items():
        key = env.get(var, "").strip()
        if not key:
            continue
        if name == "openrouter":
            providers[name] = openrouter.build(
                key,
                site_url=env.get("OPENROUTER_SITE_URL") or None,
                app_name=env.get("OPENROUTER_APP_NAME") or None,
                transport=transport,
            )
        elif name == "groq":
            providers[name] = groq.build(key, transport=transport)
        elif name == "mistral":
            providers[name] = mistral.build(key, transport=transport)
        elif name == "aihubmix":
            providers[name] = aihubmix.build(key, transport=transport)
        else:
            providers[name] = nvidia.build(key, transport=transport)

    gemini_key = env.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        providers["gemini"] = gemini.GeminiProvider(gemini_key, transport=transport)
    return providers


__all__ = [
    "Provider",
    "aihubmix",
    "build_providers",
    "gemini",
    "groq",
    "mistral",
    "nvidia",
    "openrouter",
]
