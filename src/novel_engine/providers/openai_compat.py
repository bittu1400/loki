"""OpenAI-compatible chat-completions provider.

Covers OpenRouter, Groq, Mistral, NVIDIA NIM, and the local llama.cpp
lane — all speak the same wire format, so one class parameterised by base
URL serves them all. `api_key=None` sends no Authorization header, for
servers that do not authenticate.
Status codes map onto the outcome taxonomy; expected API failures are
Outcomes, never exceptions.
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

#: Status-code buckets shared by all HTTP-speaking providers.
PERMANENT_STATUSES = {401, 402, 403}


class OpenAICompatProvider(Provider):
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str | None,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        # A local server does not authenticate; sending an empty bearer
        # token is worse than sending none.
        self._headers = {
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
            **(extra_headers or {}),
        }
        self._timeout = timeout
        self._transport = transport  # test seam; None uses real networking

    def build_payload(self, request: GenerationRequest) -> dict[str, Any]:
        """The exact request body we would send. Used by --dry-run and tests;
        lets prompt tuning inspect payloads without spending quota."""
        payload: dict[str, Any] = {
            "model": request.model_id,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def generate(self, request: GenerationRequest) -> Outcome:
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.post(
                    self._url,
                    headers=self._headers,
                    json=self.build_payload(request),
                )
        except httpx.TimeoutException:
            return TransientFailure(message="request timed out")
        except httpx.ConnectError as exc:
            # Nothing is listening. Retrying in place will not start a
            # server, but another provider can still answer — so this is
            # model-unavailable, not transient (invariant 3).
            return ModelUnavailable(message=f"cannot reach {self._url}: {exc}")
        except httpx.HTTPError as exc:
            return TransientFailure(message=f"connection error: {exc}")

        return self._outcome_from(response, requested_model=request.model_id)

    def _outcome_from(
        self, response: httpx.Response, *, requested_model: str
    ) -> Outcome:
        if response.status_code == 200:
            body = response.json()
            choice = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            return Success(
                content=choice or "",
                # Providers echo the serving model; record what actually answered.
                model_id=body.get("model", requested_model),
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                latency_ms=0,  # set by callers that measure wall time
            )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            seconds = float(retry_after) if _is_number(retry_after) else None
            return RateLimited(
                message=_error_text(response), retry_after_seconds=seconds
            )
        if response.status_code == 404:
            return ModelUnavailable(message=_error_text(response), status_code=404)
        if response.status_code in PERMANENT_STATUSES:
            return PermanentFailure(
                message=_error_text(response), status_code=response.status_code
            )
        return TransientFailure(
            message=_error_text(response), status_code=response.status_code
        )


def _is_number(value: str | None) -> bool:
    try:
        float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = body.get("error")
    if isinstance(error, dict):
        return f"HTTP {response.status_code}: {error.get('message', '')[:300]}"
    return f"HTTP {response.status_code}: {str(body)[:300]}"
