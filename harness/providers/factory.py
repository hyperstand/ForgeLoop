"""Configuration-driven provider construction. No orchestrator rewrites to switch models."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from .anthropic import AnthropicProvider
from .base import ModelProvider
from .mock_provider import MockProvider
from .openai_compat import OpenAICompatProvider


def _expand(value: Any) -> Any:
    if isinstance(value, str) and "${" in value:
        # Support ${VAR:-default} expansion.
        out = value
        while "${" in out:
            start = out.index("${") + 2
            end = out.index("}", start)
            expr = out[start:end]
            var, _, default = expr.partition(":-")
            out = out[: start - 2] + os.environ.get(var, default) + out[end + 1 :]
        return out
    return value


def from_dict(cfg: Dict[str, Any], name: str | None = None) -> ModelProvider:
    providers = cfg.get("providers", {})
    chosen = name or cfg.get("default", "mock")
    if chosen not in providers:
        raise KeyError(f"unknown provider '{chosen}' (have: {sorted(providers)})")
    spec = {k: _expand(v) for k, v in providers[chosen].items()}
    kind = spec.pop("kind", chosen)
    if kind == "mock":
        return MockProvider(model=spec.get("model", "mock-1"))
    if kind == "openai_compat":
        return OpenAICompatProvider(base_url=spec.get("base_url"), model=spec.get("model"),
                                    api_key=spec.get("api_key", os.environ.get("OPENAI_API_KEY", "")))
    if kind == "anthropic":
        return AnthropicProvider(base_url=spec.get("base_url"), model=spec.get("model"),
                                 api_key=spec.get("api_key", os.environ.get("ANTHROPIC_API_KEY", "")))
    raise KeyError(f"unknown provider kind: {kind}")


def from_yaml(path: str | Path, name: str | None = None) -> ModelProvider:
    return from_dict(yaml.safe_load(Path(path).read_text()), name)
