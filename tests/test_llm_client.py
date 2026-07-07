import json
import urllib.error

import pytest

from scripts import llm_client


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def test_chat_completions_url_appends_path_when_needed():
    assert llm_client.chat_completions_url("https://example/v1") == "https://example/v1/chat/completions"
    assert llm_client.chat_completions_url("https://example/v1/chat/completions") == "https://example/v1/chat/completions"


def test_request_headers_omit_empty_api_key():
    assert "Authorization" not in llm_client.request_headers("")
    assert llm_client.request_headers("secret")["Authorization"] == "Bearer secret"


def test_post_chat_completion_sends_openai_compatible_payload(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8"))

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    response = llm_client.post_chat_completion(
        base_url="https://example/v1",
        api_key="secret",
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        timeout=7,
    )

    assert response["choices"][0]["message"]["content"] == "ok"
    request, timeout = calls[0]
    assert request.full_url == "https://example/v1/chat/completions"
    assert timeout == 7
    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "test-model"
    assert request.headers["Authorization"] == "Bearer secret"


def test_post_chat_completion_reports_http_error(monkeypatch):
    class FakeHttpError(urllib.error.HTTPError):
        def read(self):
            return b"bad request"

    def fake_urlopen(request, timeout):
        raise FakeHttpError("https://example", 400, "Bad", {}, None)

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(llm_client.LlmClientError, match="HTTP 400"):
        llm_client.post_chat_completion(
            base_url="https://example/v1",
            api_key="",
            model="test",
            messages=[],
            tools=[],
        )


def test_extract_message_validates_response_shape():
    assert llm_client.extract_message({"choices": [{"message": {"content": "ok"}}]})["content"] == "ok"
    with pytest.raises(llm_client.LlmClientError, match="choices"):
        llm_client.extract_message({})
    with pytest.raises(llm_client.LlmClientError, match="message"):
        llm_client.extract_message({"choices": [{}]})


def test_client_from_environment_and_complete(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://example/v1")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_client,
        "post_chat_completion",
        lambda **kwargs: {"choices": [{"message": {"content": kwargs["model"]}}]},
    )

    client = llm_client.OpenAICompatibleClient.from_environment(timeout=3, temperature=0.1)

    assert client.complete([], [])["content"] == "test-model"


def test_require_env_raises_when_missing():
    """require_env поднимает LlmClientError, если переменная не задана."""
    with pytest.raises(llm_client.LlmClientError, match="MISSING_VAR"):
        llm_client.require_env("MISSING_VAR")


def test_post_chat_completion_reports_url_error(monkeypatch):
    """URLError превращается в LlmClientError."""
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(llm_client.LlmClientError, match="request failed"):
        llm_client.post_chat_completion(
            base_url="https://example/v1",
            api_key="",
            model="test",
            messages=[],
            tools=[],
        )


def test_post_chat_completion_reports_invalid_json(monkeypatch):
    """Невалидный JSON превращается в LlmClientError."""
    def fake_urlopen(request, timeout):
        return FakeResponse(b"not json at all")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(llm_client.LlmClientError, match="invalid JSON"):
        llm_client.post_chat_completion(
            base_url="https://example/v1",
            api_key="",
            model="test",
            messages=[],
            tools=[],
        )
