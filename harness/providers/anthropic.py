"""Anthropic Messages API provider (stdlib urllib, no vendor SDK).

Genuinely different backend from OpenAI-compatible: `x-api-key` auth,
`anthropic-version` header, content-block messages, `tool_use`/`tool_result`
blocks instead of `tool_calls`. Tool-calling capability is probed from the
response shape; failures normalize to ProviderError.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List

from .base import ChatMessage, ModelProvider, ProviderError, ProviderResult, ToolCallRequest, ToolSpec, Usage

VERSION = "2023-06-01"


def _to_anthropic(messages: List[ChatMessage], tools: List[ToolSpec]) -> Dict[str, Any]:
    system_parts: List[str] = []
    conv: List[Dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        elif m.role == "tool_result":
            conv.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}]})
        elif m.role == "assistant" and m.tool_calls:
            blocks: List[Dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [{"type": "tool_use", "id": t.id, "name": t.name, "input": t.arguments} for t in m.tool_calls]
            conv.append({"role": "assistant", "content": blocks})
        else:
            role = m.role if m.role in ("user", "assistant") else "user"
            conv.append({"role": role, "content": m.content})
    body: Dict[str, Any] = {"messages": conv}
    if system_parts:
        body["system"] = "\n".join(system_parts)
    if tools:
        body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in tools]
    return body


def _from_anthropic(data: Dict[str, Any], fallback_model: str) -> ProviderResult:
    try:
        blocks = data["content"]
    except KeyError as e:
        raise ProviderError("bad_request", f"unexpected response shape: {e}", False)
    text, calls = "", []
    for b in blocks:
        if b.get("type") == "text":
            text += b.get("text", "")
        elif b.get("type") == "tool_use":
            args = b.get("input", {})
            if not isinstance(args, dict):
                args = {}
            calls.append(ToolCallRequest(id=b.get("id", ""), name=b.get("name", ""), arguments=args))
    usage = data.get("usage", {})
    return ProviderResult(
        message=ChatMessage(role="assistant", content=text, tool_calls=calls),
        usage=Usage(tokens_in=int(usage.get("input_tokens", 0)), tokens_out=int(usage.get("output_tokens", 0))),
        model=data.get("model", fallback_model),
        raw=data,
    )


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None, max_tokens: int = 1024):
        self.base_url = (base_url or os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")).rstrip("/")
        self.model = model or os.environ.get("HARNESS_ANTHROPIC_MODEL", os.environ.get("HARNESS_MODEL", "claude-sonnet-4-5"))
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.max_tokens = max_tokens

    def complete(self, messages, tools, timeout_s: float = 60.0, **params) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("missing_creds", "ANTHROPIC_API_KEY is not set", False)
        body = {"model": self.model, "max_tokens": self.max_tokens, **_to_anthropic(messages, tools), **params}
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-api-key": self.api_key,
                     "anthropic-version": VERSION},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode())
        except ProviderError:
            raise
        except Exception as e:
            msg = str(e)
            if "401" in msg or "403" in msg:
                raise ProviderError("auth", msg, False)
            if "429" in msg:
                raise ProviderError("rate_limit", msg, True)
            if "timed out" in msg.lower():
                raise ProviderError("timeout", msg, True)
            raise ProviderError("transport", msg, True)
        return _from_anthropic(data, self.model)

    def capabilities(self) -> Dict[str, Any]:
        return {"tool_calling": True, "streaming": False, "max_context": 200000}
