"""OpenAI-compatible HTTP provider (stdlib urllib, no vendor SDK)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List

from .base import ChatMessage, ModelProvider, ProviderError, ProviderResult, ToolCallRequest, ToolSpec, Usage


def _to_wire(messages: List[ChatMessage], tools: List[ToolSpec], model: str) -> Dict[str, Any]:
    wire: List[Dict[str, Any]] = []
    for m in messages:
        if m.role == "tool_result":
            wire.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            wire.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": t.id,
                            "type": "function",
                            "function": {"name": t.name, "arguments": json.dumps(t.arguments)},
                        }
                        for t in m.tool_calls
                    ],
                }
            )
        else:
            wire.append({"role": m.role if m.role in ("system", "user", "assistant") else "user", "content": m.content})
    payload: Dict[str, Any] = {"model": model, "messages": wire}
    if tools:
        payload["tools"] = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}}
            for t in tools
        ]
    return payload


def _from_wire(data: Dict[str, Any], fallback_model: str) -> ProviderResult:
    try:
        choice = data["choices"][0]["message"]
    except (KeyError, IndexError) as e:
        raise ProviderError("bad_request", f"unexpected response shape: {e}", False)
    calls: List[ToolCallRequest] = []
    for tc in choice.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            # Non-tool models sometimes emit prose; surface as text, not a call.
            return ProviderResult(
                message=ChatMessage(role="assistant", content=json.dumps(choice.get("content") or "")),
                usage=Usage(),
                model=data.get("model", fallback_model),
                raw=data,
            )
        calls.append(ToolCallRequest(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))
    usage = data.get("usage", {})
    return ProviderResult(
        message=ChatMessage(role="assistant", content=choice.get("content") or "", tool_calls=calls),
        usage=Usage(tokens_in=int(usage.get("prompt_tokens", 0)), tokens_out=int(usage.get("completion_tokens", 0))),
        model=data.get("model", fallback_model),
        raw=data,
    )


class OpenAICompatProvider(ModelProvider):
    name = "openai_compat"

    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("HARNESS_MODEL", "gpt-4o-mini")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")

    def complete(self, messages, tools, timeout_s: float = 60.0, **params) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("missing_creds", "OPENAI_API_KEY is not set", False)
        body = json.dumps({**_to_wire(messages, tools, self.model), **params}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode())
        except ProviderError:
            raise
        except Exception as e:  # transport-level normalization
            msg = str(e)
            if "401" in msg or "403" in msg:
                raise ProviderError("auth", msg, False)
            if "429" in msg:
                raise ProviderError("rate_limit", msg, True)
            if "timed out" in msg.lower():
                raise ProviderError("timeout", msg, True)
            raise ProviderError("transport", msg, True)
        return _from_wire(data, self.model)
