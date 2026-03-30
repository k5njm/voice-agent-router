"""Skill executor for template and LLM-backed skills."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ..entity_cache import EntityCache
from .loader import SkillDefinition

_LOGGER = logging.getLogger(__name__)


class SkillExecutor:
    """Executes skills — either via Jinja2 templates or by returning LLM context."""

    def __init__(self, hass: HomeAssistant, entity_cache: EntityCache) -> None:
        self._hass = hass
        self._cache = entity_cache

    async def execute_template_skill(self, skill: SkillDefinition) -> str:
        """Execute a template-based skill (requires_llm=False).

        Renders the Jinja2 response_template with entity states as context.
        Returns the rendered speech text.
        """
        from homeassistant.exceptions import TemplateError
        from homeassistant.helpers.template import Template

        if not skill.response_template:
            _LOGGER.warning("Skill '%s' has no response template", skill.name)
            return f"The {skill.name} skill has no response template."

        # Build template variables from requested entities
        variables: dict[str, Any] = {}
        entity_states: dict[str, Any] = {}

        for entity_pattern in skill.entities:
            try:
                if "*" in entity_pattern:
                    # Glob pattern like binary_sensor.*_door*
                    domain = entity_pattern.split(".")[0]
                    for state in self._cache.get_entities_by_domain(domain):
                        entity_states[state.entity_id] = state
                else:
                    state = self._cache.get_entity_state(entity_pattern)
                    if state is not None:
                        entity_states[entity_pattern] = state
                    else:
                        _LOGGER.debug(
                            "Entity '%s' not found in cache for skill '%s'",
                            entity_pattern,
                            skill.name,
                        )
            except Exception:
                _LOGGER.exception(
                    "Error resolving entity pattern '%s' for skill '%s'",
                    entity_pattern,
                    skill.name,
                )

        variables["states"] = entity_states
        variables["entity_states"] = entity_states

        try:
            template = Template(skill.response_template, self._hass)
            return template.async_render(variables)
        except TemplateError as err:
            _LOGGER.error("Jinja2 template error in skill '%s': %s", skill.name, err)
            return f"Sorry, I had trouble running the {skill.name} skill."
        except Exception:
            _LOGGER.exception("Unexpected error rendering template for skill '%s'", skill.name)
            return f"Sorry, I had trouble running the {skill.name} skill."

    def get_llm_skill_context(self, skill: SkillDefinition) -> dict[str, Any]:
        """Get the LLM context for an LLM-backed skill.

        Returns a dict with system_prompt and tools list for the cloud path.
        """
        return {
            "system_prompt": skill.system_prompt,
            "tools": skill.tools,
            "skill_name": skill.name,
        }
