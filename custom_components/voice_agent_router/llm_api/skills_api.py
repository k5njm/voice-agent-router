"""Skills exposed as Home Assistant LLM API tools."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from ..skills.loader import SkillLoader

_LOGGER = logging.getLogger(__name__)

SKILLS_API_ID = "voice_agent_router_skills"


class SkillTool(llm.Tool):
    """A skill wrapped as an HA LLM Tool."""

    def __init__(self, skill_name: str, description: str) -> None:
        self.name = f"skill_{skill_name}"
        self.description = description
        self.parameters = vol.Schema({})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Invoke the skill — actual execution happens in the conversation entity."""
        return {"skill": self.name, "status": "invoked"}


class SkillsAPI(llm.API):
    """LLM API that exposes loaded skills as callable tools."""

    def __init__(self, hass: HomeAssistant, skill_loader: SkillLoader) -> None:
        super().__init__(
            hass=hass,
            id=SKILLS_API_ID,
            name="Voice Agent Router Skills",
        )
        self._loader = skill_loader

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Build the API instance with current skills as tools."""
        tools = [
            SkillTool(name, skill.description)
            for name, skill in self._loader.skills.items()
            if skill.requires_llm
        ]

        return llm.APIInstance(
            api=self,
            api_prompt="You have access to custom skills. Use them when relevant.",
            llm_context=llm_context,
            tools=tools,
        )
