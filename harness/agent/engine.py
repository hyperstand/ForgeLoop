"""Bounded agent execution loop. Model proposes; registry disposes."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from ..providers.base import ChatMessage, ModelProvider, ProviderError, ToolCallRequest
from ..security.policy import enforce_output_cap
from ..tools.registry import ToolContext, ToolError, ToolRegistry


@dataclass
class EngineConfig:
    max_iterations: int = 12
    wall_clock_s: float = 300.0
    token_budget: int = 60000
    max_tool_calls: int = 30
    max_output_bytes: int = 65536
    retries: int = 2


@dataclass
class AgentResult:
    status: str  # completed | failed | blocked_needs_approval | blocked_needs_clarification | budget_exceeded
    summary: str
    files_changed: List[str] = field(default_factory=list)
    diff: str = ""
    validation: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, int] = field(default_factory=lambda: {"tokens_in": 0, "tokens_out": 0, "tool_calls": 0})
    trace_id: str = ""


def _msg_to_dict(m: ChatMessage) -> Dict[str, Any]:
    return {"role": m.role, "content": m.content,
            "tool_calls": [{"id": t.id, "name": t.name, "arguments": t.arguments} for t in m.tool_calls],
            "tool_call_id": m.tool_call_id, "name": m.name}


def _msg_from_dict(d: Dict[str, Any]) -> ChatMessage:
    return ChatMessage(role=d["role"], content=d.get("content", ""),
                       tool_calls=[ToolCallRequest(id=t.get("id", ""), name=t["name"],
                                                   arguments=t.get("arguments", {}))
                                   for t in d.get("tool_calls", [])],
                       tool_call_id=d.get("tool_call_id", ""), name=d.get("name", ""))


class AgentEngine:
    def __init__(self, provider: ModelProvider, registry: ToolRegistry, config: EngineConfig | None = None):
        self.provider = provider
        self.registry = registry
        self.config = config or EngineConfig()

    def run(
        self,
        task: str,
        worktree: Path,
        instructions: str = "",
        ctx_extra: Dict[str, Any] | None = None,
        checkpoint_path: Path | str | None = None,
        resume_from: Path | str | None = None,
    ) -> AgentResult:
        t0 = time.time()
        usage = {"tokens_in": 0, "tokens_out": 0, "tool_calls": 0}
        ctx = ToolContext(worktree=Path(worktree))
        if resume_from and Path(resume_from).is_file():
            saved = json.loads(Path(resume_from).read_text())
            messages = [_msg_from_dict(d) for d in saved["messages"]]
            usage.update(saved.get("usage", {}))
        else:
            system = "You are a coding agent. Use only the provided tools. Ask for clarification when evidence is insufficient."
            if instructions:
                system += "\n\n--- project-doc ---\n" + instructions[:32768]
            messages = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=task)]
        tool_log: List[Dict[str, Any]] = []

        def _checkpoint() -> None:
            if checkpoint_path:
                p = Path(checkpoint_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"messages": [_msg_to_dict(m) for m in messages], "usage": usage}))

        for _ in range(self.config.max_iterations):
            if time.time() - t0 > self.config.wall_clock_s:
                return AgentResult("budget_exceeded", "wall-clock exceeded", usage=usage)
            specs = self.registry.list_specs("all")
            attempt = 0
            while True:
                try:
                    res = self.provider.complete(messages, specs, timeout_s=60.0)
                    break
                except ProviderError as e:
                    if e.retryable and attempt < self.config.retries:
                        attempt += 1
                        continue
                    return AgentResult("failed", f"provider error: {e}", usage=usage)
            usage["tokens_in"] += res.usage.tokens_in
            usage["tokens_out"] += res.usage.tokens_out
            if usage["tokens_in"] + usage["tokens_out"] > self.config.token_budget:
                return AgentResult("budget_exceeded", "token budget exceeded", usage=usage)
            msg = res.message
            messages.append(msg)
            _checkpoint()
            if not msg.tool_calls:
                text = enforce_output_cap(msg.content or "", self.config.max_output_bytes)
                return AgentResult("completed", text, usage=usage)
            for tc in msg.tool_calls:
                if usage["tool_calls"] >= self.config.max_tool_calls:
                    return AgentResult("budget_exceeded", "tool-call budget exceeded", usage=usage)
                usage["tool_calls"] += 1
                try:
                    out = self.registry.dispatch(tc.name, tc.arguments, ctx)
                    body = enforce_output_cap(str(out)[: self.config.max_output_bytes], self.config.max_output_bytes)
                except (ToolError, Exception) as e:  # tool failures are model-visible, not fatal
                    body = f"TOOL_ERROR {type(e).__name__}: {e}"
                tool_log.append({"tool": tc.name, "args": tc.arguments})
                messages.append(ChatMessage(role="tool_result", content=body, tool_call_id=tc.id, name=tc.name))
                _checkpoint()
        _checkpoint()
        return AgentResult("budget_exceeded", "iteration budget exceeded", usage=usage)
