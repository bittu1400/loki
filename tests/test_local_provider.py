"""Local llama.cpp lane (ADR-0006): no auth header, context clamping, and
a server that is not running being fallback-eligible rather than fatal."""

import json

import httpx
import pytest

from novel_engine.core.config import KEYLESS_PROVIDERS, KNOWN_PROVIDERS
from novel_engine.providers.base import (
    GenerationRequest,
    ModelUnavailable,
    Success,
)
from novel_engine.providers.local import (
    DEFAULT_CONTEXT_WINDOW,
    MIN_OUTPUT_TOKENS,
    LocalProvider,
    build,
)

OK_BODY = {
    "choices": [{"message": {"content": "prose"}}],
    "model": "gemma-4-12b-it",
    "usage": {"prompt_tokens": 1686, "completion_tokens": 1406},
}


def request(prompt: str = "write a chapter", max_tokens: int = 4096):
    return GenerationRequest(
        prompt=prompt,
        model_id="gemma-4-12b-it",
        max_tokens=max_tokens,
        temperature=0.9,
        top_p=0.95,
    )


def provider_capturing(sent: list[httpx.Request], **kwargs) -> LocalProvider:
    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(req)
        return httpx.Response(200, json=OK_BODY)

    return LocalProvider(transport=httpx.MockTransport(handler), **kwargs)


def test_no_authorization_header_is_sent():
    sent: list[httpx.Request] = []
    outcome = provider_capturing(sent).generate(request())

    assert isinstance(outcome, Success)
    assert "authorization" not in {key.lower() for key in sent[0].headers}


def test_server_not_running_is_model_unavailable_not_permanent():
    def refuse(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=req)

    outcome = LocalProvider(transport=httpx.MockTransport(refuse)).generate(request())

    # Fallback-eligible (invariant 3): another provider can still answer.
    assert isinstance(outcome, ModelUnavailable)
    assert "cannot reach" in outcome.message


def test_max_tokens_is_clamped_to_what_the_window_allows():
    sent: list[httpx.Request] = []
    prompt = "word " * 2000  # ~10k chars, ~2900 estimated tokens
    provider = provider_capturing(sent, context_window=4096)

    provider.generate(request(prompt, max_tokens=4096))

    payload = json.loads(sent[0].content)
    assert payload["max_tokens"] == provider.room_for_output(prompt)
    assert payload["max_tokens"] < 4096


def test_small_prompt_keeps_the_requested_max_tokens():
    sent: list[httpx.Request] = []
    provider_capturing(sent, context_window=100_000).generate(request(max_tokens=2400))

    assert json.loads(sent[0].content)["max_tokens"] == 2400


def test_prompt_with_no_room_left_refuses_before_calling():
    called: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        called.append(req)
        return httpx.Response(200, json=OK_BODY)

    provider = LocalProvider(
        context_window=1024, transport=httpx.MockTransport(handler)
    )
    outcome = provider.generate(request("word " * 1000))

    assert isinstance(outcome, ModelUnavailable)
    assert str(MIN_OUTPUT_TOKENS) in outcome.message
    assert called == []  # never left the machine


@pytest.mark.parametrize(
    ("env", "expected_url", "expected_window"),
    [
        ({}, "http://localhost:8080/v1/chat/completions", DEFAULT_CONTEXT_WINDOW),
        (
            {
                "LOCAL_BASE_URL": "http://127.0.0.1:9000/v1",
                "LOCAL_CONTEXT_WINDOW": "32768",
            },
            "http://127.0.0.1:9000/v1/chat/completions",
            32768,
        ),
        ({"LOCAL_CONTEXT_WINDOW": "not-a-number"}, None, DEFAULT_CONTEXT_WINDOW),
    ],
)
def test_build_honours_environment_overrides(env, expected_url, expected_window):
    provider = build(env)
    assert provider.context_window == expected_window
    if expected_url:
        assert provider._url == expected_url


def test_local_needs_no_key_at_startup_validation():
    assert "local" in KNOWN_PROVIDERS
    assert "local" in KEYLESS_PROVIDERS
