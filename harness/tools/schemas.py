"""Minimal JSON-schema-subset validation for tool arguments."""
from __future__ import annotations

from typing import Any, Dict


class ValidationError(Exception):
    pass


def validate(args: Dict[str, Any], schema: Dict[str, Any], tool: str = "") -> Dict[str, Any]:
    if not isinstance(args, dict):
        raise ValidationError(f"{tool}: args must be an object")
    props = schema.get("properties", {})
    for req in schema.get("required", []):
        if req not in args:
            raise ValidationError(f"{tool}: missing required arg '{req}'")
    out: Dict[str, Any] = {}
    for k, v in args.items():
        if k in props:
            _check_type(tool, k, v, props[k].get("type"))
            out[k] = v
        # unknown args are dropped (strict tools ignore extras) — documented
    # defaults
    for k, spec in props.items():
        if k not in out and "default" in spec:
            out[k] = spec["default"]
    return out


def _check_type(tool: str, name: str, value: Any, want: Any) -> None:
    if want is None:
        return
    ok = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(want, True)
    if not ok:
        raise ValidationError(f"{tool}: arg '{name}' must be {want}")
