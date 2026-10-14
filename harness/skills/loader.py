"""Skill discovery: metadata-first, body on use (progressive disclosure)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    body: str = ""  # loaded lazily


def _parse_skill_md(p: Path) -> Skill:
    text = p.read_text()
    name, desc = p.parent.name, ""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
    return Skill(name=name, description=desc, path=p, body=text)


class SkillRegistry:
    def __init__(self) -> None:
        self.skills: Dict[str, Skill] = {}

    def discover(self, root: Path) -> "SkillRegistry":
        for md in Path(root).rglob("*/SKILL.md"):
            try:
                s = _parse_skill_md(md)
            except OSError:
                continue
            self.skills.setdefault(s.name, s)
        return self

    def catalog(self) -> List[Dict[str, str]]:
        return [{"name": s.name, "description": s.description} for s in self.skills.values()]

    def load(self, name: str) -> Skill:
        return self.skills[name]
