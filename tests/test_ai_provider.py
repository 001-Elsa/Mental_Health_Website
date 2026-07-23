import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx

from backend.services import ai_client as ai_module
from backend.services.ai_client import AIClient, AIProviderError, FALLBACK_REPLY


def provider_settings():
    return SimpleNamespace(
        ai_max_concurrency=2,
        ai_max_retries=2,
        ai_retry_base_seconds=0,
        ai_connect_timeout_seconds=0.1,
        ai_read_timeout_seconds=0.1,
        ai_max_connections=2,
        deepseek_api_key="controlled-test-key",
        deepseek_url="https://provider.invalid/chat",
    )


def successful_response(content="稳定回复"):
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def test_ai_provider_retries_429_then_recovers(monkeypatch):
    monkeypatch.setattr(ai_module, "get_settings", provider_settings)
    monkeypatch.setattr(ai_module.asyncio, "sleep", AsyncMock())
    client = AIClient()
    client._post = AsyncMock(side_effect=[AIProviderError("rate_limited", retryable=True), successful_response()])

    result = asyncio.run(client._request([{"role": "user", "content": "hello"}], temperature=0, max_tokens=20))

    assert result == "稳定回复"
    assert client._post.await_count == 2


def test_ai_provider_retries_timeout_only_up_to_budget(monkeypatch):
    monkeypatch.setattr(ai_module, "get_settings", provider_settings)
    monkeypatch.setattr(ai_module.asyncio, "sleep", AsyncMock())
    client = AIClient()
    client._post = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))

    try:
        asyncio.run(client._request([{"role": "user", "content": "hello"}], temperature=0, max_tokens=20))
        raise AssertionError("request should fail after the retry budget")
    except AIProviderError as exc:
        assert exc.reason == "read_timeout"
    assert client._post.await_count == 3


def test_ai_provider_invalid_response_does_not_retry_and_chat_degrades(monkeypatch):
    monkeypatch.setattr(ai_module, "get_settings", provider_settings)
    client = AIClient()
    invalid = Mock()
    invalid.json.return_value = {"choices": []}
    client._post = AsyncMock(return_value=invalid)

    result = asyncio.run(client.chat([], "最近压力很大"))

    assert result == FALLBACK_REPLY
    assert client._post.await_count == 1
