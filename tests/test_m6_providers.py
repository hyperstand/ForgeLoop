"""M6 provider tests: Anthropic adapter (mocked HTTP), factory, error normalization."""
import io
import json
import urllib.request

import pytest

from harness.providers.anthropic import AnthropicProvider, _from_anthropic, _to_anthropic
from harness.providers.base import ChatMessage, ProviderError, ToolSpec
from harness.providers.factory import from_dict, from_yaml


class _FakeResp:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


def _anthropic_ok():
    return {"id": "msg_1", "model": "claude-sonnet-4-5",
            "content": [{"type": "text", "text": "hi"},
                        {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "a.py"}}],
            "usage": {"input_tokens": 7, "output_tokens": 3}}


def test_anthropic_wire_format_differs_from_openai():
    body = _to_anthropic([ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="do")],
                         [ToolSpec(name="read_file", description="r", schema={"type": "object"})])
    assert body["system"] == "sys"
    assert body["tools"][0]["input_schema"] == {"type": "object"}  # not 'parameters'
    assert body["messages"][0]["role"] == "user"


def test_anthropic_parses_tool_use_blocks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _FakeResp(_anthropic_ok()))
    res = AnthropicProvider().complete([ChatMessage(role="user", content="do")], [])
    assert res.message.content == "hi"
    assert res.message.tool_calls[0].name == "read_file"
    assert res.message.tool_calls[0].arguments == {"path": "a.py"}
    assert (res.usage.tokens_in, res.usage.tokens_out) == (7, 3)


def test_anthropic_missing_creds_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError) as e:
        AnthropicProvider(api_key="").complete([ChatMessage(role="user", content="x")], [])
    assert e.value.code == "missing_creds" and not e.value.retryable


def test_anthropic_transport_normalized(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    def boom(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ProviderError) as e:
        AnthropicProvider().complete([ChatMessage(role="user", content="x")], [])
    assert e.value.code == "timeout" and e.value.retryable


def test_anthropic_bad_shape():
    with pytest.raises(ProviderError):
        _from_anthropic({"nope": 1}, "m")


def test_factory_builds_all_kinds_and_expands_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    cfg = {"default": "mock",
           "providers": {"mock": {"kind": "mock"},
                         "oai": {"kind": "openai_compat", "base_url": "${OPENAI_BASE_URL:-https://x/v1}"},
                         "ant": {"kind": "anthropic"}}}
    assert from_dict(cfg, "mock").name == "mock"
    assert from_dict(cfg, "oai").base_url == "https://x/v1"
    assert from_dict(cfg, "ant").name == "anthropic"
    assert from_dict(cfg).name == "mock"  # default
    with pytest.raises(KeyError):
        from_dict(cfg, "nope")
    p = tmp_path / "m.yaml"
    p.write_text("default: mock\nproviders:\n  mock: {kind: mock}\n")
    assert from_yaml(p).name == "mock"


def test_capabilities_report_tool_compat():
    assert AnthropicProvider(api_key="x").capabilities()["tool_calling"] is True
    from harness.providers.mock_provider import MockProvider
    assert MockProvider().capabilities()["tool_calling"] is True
