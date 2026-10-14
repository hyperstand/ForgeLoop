"""Deterministic mock provider for offline tests and demos."""
from __future__ import annotations

from typing import Any, Dict, List

from .base import ChatMessage, ModelProvider, ProviderResult, ToolSpec, Usage


class MockProvider(ModelProvider):
    name = "mock"

    def __init__(self, script: List[ProviderResult] | None = None, model: str = "mock-1"):
        self._script: List[ProviderResult] = list(script or [])
        self.model = model
        self.calls: List[Dict[str, Any]] = []

    def queue(self, result: ProviderResult) -> None:
        self._script.append(result)

    def complete(
        self,
        messages: List[ChatMessage],
        tools: List[ToolSpec],
        timeout_s: float = 60.0,
        **params: Any,
    ) -> ProviderResult:
        self.calls.append({"messages": len(messages), "tools": [t.name for t in tools]})
        if self._script:
            res = self._script.pop(0)
            res.model = res.model or self.model
            return res
        last = messages[-1].content if messages else ""
        return ProviderResult(
            message=ChatMessage(role="assistant", content=f"mock-echo: {last[:200]}"),
            usage=Usage(tokens_in=10, tokens_out=5),
            model=self.model,
        )

    def capabilities(self) -> Dict[str, Any]:
        return {"tool_calling": True, "streaming": False, "max_context": 8192}


def assistant_text(text: str, model: str = "mock-1") -> ProviderResult:
    from .base import Usage as _U

    return ProviderResult(message=ChatMessage(role="assistant", content=text), usage=_U(5, 5), model=model)


def assistant_tool_calls(calls: List[Dict[str, Any]], model: str = "mock-1") -> ProviderResult:
    from .base import ChatMessage as _M, ProviderResult as _R, ToolCallRequest as _T, Usage as _U

    reqs = [_T(id=c.get("id", f"call_{i}"), name=c["name"], arguments=c.get("arguments", {})) for i, c in enumerate(calls)]
    return _R(message=_M(role="assistant", content="", tool_calls=reqs), usage=_U(5, 5), model=model)
