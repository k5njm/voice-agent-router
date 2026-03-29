"""YAML skill loader with directory watching."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_LOGGER = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """A loaded skill definition."""
    name: str
    description: str
    trigger_patterns: list[str]
    requires_llm: bool = False
    system_prompt: str = ""
    response_template: str = ""
    tools: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


class SkillLoader:
    """Loads and manages skill definitions from YAML files."""

    def __init__(self, skills_dir: str | Path) -> None:
        self._dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}

    async def async_load(self) -> None:
        """Load all skill YAML files from the configured directory."""
        self._skills.clear()
        if not self._dir.exists():
            _LOGGER.warning("Skills directory does not exist: %s", self._dir)
            return

        for path in self._dir.glob("*.yaml"):
            try:
                skill = self._parse_skill(path)
                self._skills[skill.name] = skill
                _LOGGER.debug("Loaded skill: %s", skill.name)
            except Exception:
                _LOGGER.exception("Failed to load skill: %s", path)

        _LOGGER.info("Loaded %d skills", len(self._skills))

    def _parse_skill(self, path: Path) -> SkillDefinition:
        """Parse a single YAML skill file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        trigger = data.get("trigger", {})
        return SkillDefinition(
            name=data["name"],
            description=data.get("description", ""),
            trigger_patterns=[p.lower() for p in trigger.get("patterns", [])],
            requires_llm=data.get("requires_llm", False),
            system_prompt=data.get("system_prompt", ""),
            response_template=data.get("response_template", ""),
            tools=data.get("tools", []),
            entities=data.get("entities", []),
        )

    def match(self, text: str) -> SkillDefinition | None:
        """Find a skill whose trigger patterns match the input text."""
        cleaned = text.strip().lower()
        for skill in self._skills.values():
            for pattern in skill.trigger_patterns:
                if pattern in cleaned:
                    return skill
        return None

    @property
    def skills(self) -> dict[str, SkillDefinition]:
        return dict(self._skills)

    async def async_reload(self) -> None:
        """Reload all skills from disk."""
        await self.async_load()
