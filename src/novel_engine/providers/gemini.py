"""Google Gemini (AI Studio) provider.

Uses the generateContent REST endpoint. Status mapping matches the shared
taxonomy; Gemini's 503 "high demand" is the canonical TransientFailure we
observed during the August 2026 spike.
"""

from __future__ import annotations

from typing import Any

import httpx

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
from novel_engine.providers.openai_compat import _is_number

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def build_payload(self, request: GenerationRequest) -> dict[str, Any]:
        config: dict[str, Any] = {
            "temperature": request.temperature,
            "topP": request.top_p,
            "maxOutputTokens": request.max_tokens,
        }
        if request.json_mode:
            config["responseMimeType"] = "application/json"
        return {
            "contents": [{"parts": [{"text": request.prompt}]}],
            "generationConfig": config,
        }

    def generate(self, request: GenerationRequest) -> Outcome:
        url = f"{BASE_URL}/models/{request.model_id}:generateContent"
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.post(
                    url,
                    params={"key": self._api_key},
                    json=self.build_payload(request),
                )
        except httpx.TimeoutException:
            return TransientFailure(message="request timed out")
        except httpx.HTTPError as exc:
            return TransientFailure(message=f"connection error: {exc}")
        return self._outcome_from(response)

    def _outcome_from(self, response: httpx.Response) -> Outcome:
        if response.status_code == 200:
            body = response.json()
            parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
            usage = body.get("usageMetadata", {})
            return Success(
                content=content,
                model_id=body.get("modelVersion", "gemini"),
                input_tokens=int(usage.get("promptTokenCount", 0)),
                output_tokens=int(usage.get("candidatesTokenCount", 0)),
                latency_ms=0,
            )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            seconds = float(retry_after) if _is_number(retry_after) else None
            return RateLimited(
                message=_error_text(response), retry_after_seconds=seconds
            )
        if response.status_code == 404:
            return ModelUnavailable(message=_error_text(response), status_code=404)
        if response.status_code in (401, 403):
            return PermanentFailure(
                message=_error_text(response), status_code=response.status_code
            )
        # 400 can be a bad key OR a malformed prompt — both deterministic.
        if response.status_code == 400 and "API key not valid" in response.text:
            return PermanentFailure(message=_error_text(response), status_code=400)
        return TransientFailure(
            message=_error_text(response), status_code=response.status_code
        )


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = body.get("error", {})
    message = error.get("message", "") if isinstance(error, dict) else ""
    return f"HTTP {response.status_code}: {message[:300]}"
