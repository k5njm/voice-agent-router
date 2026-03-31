"""YAML skill loader with directory watching."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

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
    cache_cron: str | None = None
    cache_ttl: int = 0


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
                _LOGGER.debug("Loaded skill: %s from %s", skill.name, path)
            except yaml.YAMLError:
                _LOGGER.exception("Malformed YAML in skill file, skipping: %s", path)
            except (ValueError, KeyError):
                _LOGGER.exception("Invalid skill definition, skipping: %s", path)
            except Exception:
                _LOGGER.exception("Unexpected error loading skill, skipping: %s", path)

        _LOGGER.info("Loaded %d skills", len(self._skills))

    def _parse_skill(self, path: Path) -> SkillDefinition:
        """Parse a single YAML skill file.

        Raises on malformed YAML or missing required fields so the caller
        can log and skip.
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping, got {type(data).__name__}")

        if "name" not in data:
            raise ValueError("Skill file is missing required 'name' field")

        trigger = data.get("trigger", {})
        if not isinstance(trigger, dict):
            _LOGGER.warning(
                "Skill '%s' has invalid trigger format (expected mapping), treating as no patterns",
                data["name"],
            )
            trigger = {}

        patterns_raw = trigger.get("patterns", [])
        if not isinstance(patterns_raw, list):
            _LOGGER.warning(
                "Skill '%s' has non-list trigger patterns, treating as empty",
                data["name"],
            )
            patterns_raw = []

        cache_block = data.get("cache", {})
        if not isinstance(cache_block, dict):
            cache_block = {}

        return SkillDefinition(
            name=data["name"],
            description=data.get("description", ""),
            trigger_patterns=[str(p).lower() for p in patterns_raw],
            requires_llm=data.get("requires_llm", False),
            system_prompt=data.get("system_prompt", ""),
            response_template=data.get("response_template", ""),
            tools=data.get("tools", []),
            entities=data.get("entities", []),
            cache_cron=cache_block.get("cron"),
            cache_ttl=int(cache_block.get("ttl", 0)),
        )

    def match(self, text: str) -> SkillDefinition | None:
        """Find a skill whose trigger patterns match the input text."""
        result = self.match_with_score(text)
        if result is None:
            return None
        return result[0]

    def match_with_score(
        self, text: str, threshold: float = 0.8
    ) -> tuple[SkillDefinition, float] | None:
        """Find a skill matching the input text, returning (skill, score).

        Tries exact substring first (score 1.0), then falls back to
        token-overlap fuzzy matching above the given threshold.
        """
        cleaned = text.strip().lower()

        # Fast path: exact substring match
        for skill in self._skills.values():
            for pattern in skill.trigger_patterns:
                if pattern in cleaned:
                    return (skill, 1.0)

        # Fuzzy path: token-overlap scoring
        input_tokens = set(cleaned.split())
        best_skill: SkillDefinition | None = None
        best_score: float = 0.0

        for skill in self._skills.values():
            for pattern in skill.trigger_patterns:
                pattern_tokens = set(pattern.split())
                if not pattern_tokens or not input_tokens:
                    continue
                overlap = len(input_tokens & pattern_tokens)
                score = overlap / max(len(input_tokens), len(pattern_tokens))
                if score > best_score:
                    best_score = score
                    best_skill = skill

        if best_skill is not None and best_score >= threshold:
            return (best_skill, best_score)

        return None

    def nearest_miss(self, text: str) -> tuple[str, float] | None:
        """Return the closest skill name and score if between 0.4 and 0.8.

        Used for near-miss logging when the LLM path is taken.
        """
        cleaned = text.strip().lower()
        input_tokens = set(cleaned.split())
        best_name: str = ""
        best_score: float = 0.0

        for skill in self._skills.values():
            for pattern in skill.trigger_patterns:
                pattern_tokens = set(pattern.split())
                if not pattern_tokens or not input_tokens:
                    continue
                overlap = len(input_tokens & pattern_tokens)
                score = overlap / max(len(input_tokens), len(pattern_tokens))
                if score > best_score:
                    best_score = score
                    best_name = skill.name

        if 0.4 < best_score < 0.8:
            return (best_name, best_score)
        return None

    @property
    def skills(self) -> dict[str, SkillDefinition]:
        return dict(self._skills)

    async def async_reload(self) -> None:
        """Reload all skills from disk."""
        await self.async_load()
