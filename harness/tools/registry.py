"""Typed tool registry + router. Validates before executing."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..providers.base import ToolSpec
from .schemas import ValidationError, validate


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    worktree: Path
    evidence_ro: Path | None = None
    task_id: str = ""
    unrestricted_exec: bool = False
    timeout_s: float = 60.0
    max_output_bytes: int = 65536


@dataclass
class ToolDef:
    name: str
    description: str
    schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any], ToolContext], Any]
    risk_tier: str = "read"  # read | edit | exec | privileged
    exposure: str = "direct"  # direct | deferred | hidden
    parallel_safe: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ToolError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolError(f"unknown tool: {name}")

    def list_specs(self, exposure: str = "direct") -> List[ToolSpec]:
        specs = []
        for t in self._tools.values():
            if exposure == "all" or t.exposure == exposure or t.exposure == "direct":
                specs.append(ToolSpec(name=t.name, description=t.description, schema=t.schema))
        return specs

    def dispatch(self, name: str, args: Dict[str, Any], ctx: ToolContext) -> Any:
        tool = self.get(name)
        try:
            clean = validate(args, tool.schema, tool.name)
        except ValidationError as e:
            raise ToolError(str(e))
        return tool.handler(clean, ctx)
