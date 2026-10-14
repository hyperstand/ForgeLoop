"""Provider-neutral model interface. No SDK types leak past this module."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatMessage:
    role: str  # system | user | assistant | tool_result
    content: str = ""
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class ProviderResult:
    message: ChatMessage
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderError(Exception):
    code: str  # auth | rate_limit | timeout | bad_request | transport | missing_creds
    message: str
    retryable: bool = False

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"


class ModelProvider(abc.ABC):
    """Stable internal contract. Orchestrator depends only on this."""

    name: str = "base"

    @abc.abstractmethod
    def complete(
        self,
        messages: List[ChatMessage],
        tools: List[ToolSpec],
        timeout_s: float = 60.0,
        **params: Any,
    ) -> ProviderResult:
        ...

    def capabilities(self) -> Dict[str, Any]:
        return {"tool_calling": True, "streaming": False, "max_context": None}

    def select_model(self, model: Optional[str] = None) -> str:
        return model or getattr(self, "model", self.name)
