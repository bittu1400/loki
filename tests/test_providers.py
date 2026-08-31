"""Concrete provider tests over mocked HTTP (httpx.MockTransport).

No test here ever touches the network; live verification is a manual
OQ-02 activity, not something CI can afford on free-tier quotas.
"""

import json

import httpx
import pytest

from novel_engine.providers.base import (
    GenerationRequest,
    ModelUnavailable,
    PermanentFailure,
    RateLimited,
    Success,
    TransientFailure,
)
from novel_engine.providers.gemini import GeminiProvider
from novel_engine.providers.openai_compat import OpenAICompatProvider


def request() -> GenerationRequest:
    return GenerationRequest(prompt="hello", model_id="test-model")


def mock_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def respond(status: int, body: dict, headers: dict | None = None):
    return httpx.Response(status, json=body, headers=headers or {})


OPENAI_OK = {
    "model": "served-model",
    "choices": [{"message": {"content": "prose"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestOpenAICompat:
    def make(self, handler) -> OpenAICompatProvider:
        return OpenAICompatProvider(
            "openrouter",
            "https://x.example/v1",
            "key",
            transport=mock_transport(handler),
        )

    def test_success_maps_fields(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return respond(200, OPENAI_OK)

        outcome = self.make(handler).generate(request())
        assert isinstance(outcome, Success)
        assert outcome.content == "prose"
        assert outcome.model_id == "served-model"  # what answered, not what we asked
        assert (outcome.input_tokens, outcome.output_tokens) == (10, 5)

    def test_payload_includes_json_mode_flag(self) -> None:
        captured = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(req.content)
            return respond(200, OPENAI_OK)

        self.make(handler).generate(
            GenerationRequest(prompt="p", model_id="m", json_mode=True)
        )
        assert captured["body"]["response_format"] == {"type": "json_object"}
        assert captured["body"]["messages"][0]["content"] == "p"

    def test_429_captures_retry_after(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"error": {"message": "slow"}}, headers={"retry-after": "12"}
            )

        outcome = self.make(handler).generate(request())
        assert isinstance(outcome, RateLimited)
        assert outcome.retry_after_seconds == 12.0

    def test_auth_and_paywall_are_permanent(self) -> None:
        for status in (401, 402, 403):

            def handler(req: httpx.Request, status=status) -> httpx.Response:
                return respond(status, {"error": {"message": "no"}})

            outcome = self.make(handler).generate(request())
            assert isinstance(outcome, PermanentFailure), f"status {status}"

    def test_404_is_model_unavailable(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return respond(404, {"error": {"message": "slug pulled"}})

        assert isinstance(self.make(handler).generate(request()), ModelUnavailable)

    def test_503_is_transient(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return respond(503, {"error": {"message": "overloaded"}})

        assert isinstance(self.make(handler).generate(request()), TransientFailure)

    def test_timeout_is_transient_not_exception(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("too slow")

        outcome = self.make(handler).generate(request())
        assert isinstance(outcome, TransientFailure)

    def test_non_json_error_body_does_not_crash(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="<html>boom</html>")

        outcome = self.make(handler).generate(request())
        assert isinstance(outcome, TransientFailure)
        assert "HTTP 500" in outcome.message

    def test_openrouter_headers_present_when_configured(self) -> None:
        from novel_engine.providers import openrouter

        provider = openrouter.build(
            "key", site_url="https://example.org", app_name="novel-engine"
        )
        assert provider._headers["HTTP-Referer"] == "https://example.org"
        assert provider._headers["X-Title"] == "novel-engine"


GEMINI_OK = {
    "candidates": [{"content": {"parts": [{"text": "chapter text"}]}}],
    "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 4},
    "modelVersion": "gemini-3.5-flash-lite",
}


class TestGemini:
    def make(self, handler) -> GeminiProvider:
        return GeminiProvider("key", transport=mock_transport(handler))

    def test_success_joins_parts(self) -> None:
        outcome = self.make(lambda req: respond(200, GEMINI_OK)).generate(request())
        assert isinstance(outcome, Success)
        assert outcome.content == "chapter text"
        assert outcome.model_id == "gemini-3.5-flash-lite"

    def test_json_mode_sets_response_mime(self) -> None:
        captured = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(req.content)
            return respond(200, GEMINI_OK)

        self.make(handler).generate(
            GenerationRequest(prompt="p", model_id="m", json_mode=True)
        )
        config = captured["body"]["generationConfig"]
        assert config["responseMimeType"] == "application/json"

    def test_bad_key_is_permanent_even_on_400(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return respond(
                400,
                {
                    "error": {
                        "message": "API key not valid. Please pass a valid API key."
                    }
                },
            )

        outcome = self.make(handler).generate(request())
        assert isinstance(outcome, PermanentFailure)

    def test_high_demand_503_is_transient(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return respond(503, {"error": {"message": "high demand"}})

        outcome = self.make(handler).generate(request())
        assert isinstance(outcome, TransientFailure)


def test_build_providers_skips_missing_keys() -> None:
    from novel_engine.providers import build_providers

    providers = build_providers({"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q"})
    # "local" is always present: it needs no key (ADR-0006).
    assert set(providers) == {"gemini", "groq", "local"}


@pytest.mark.parametrize(
    "name", ["openrouter", "groq", "mistral", "nvidia", "aihubmix"]
)
def test_every_openai_compat_provider_builds(name: str) -> None:
    from novel_engine.providers import ENV_KEYS, build_providers

    env_var = ENV_KEYS[name]
    providers = build_providers({env_var: "k"})
    assert name in providers
