"""MCP tools exposed as Home Assistant LLM API."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..mcp.client import MCPClientManager

_LOGGER = logging.getLogger(__name__)

MCP_API_ID = "voice_agent_router_mcp"


class MCPAPI(llm.API):
    """LLM API that exposes MCP server tools."""

    def __init__(self, hass: HomeAssistant, mcp_manager: MCPClientManager) -> None:
        super().__init__(
            hass=hass,
            id=MCP_API_ID,
            name="Voice Agent Router MCP Tools",
        )
        self._manager = mcp_manager

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Build the API instance with all connected MCP tools."""
        return llm.APIInstance(
            api=self,
            api_prompt=(
                "You have access to tools from external MCP servers. "
                "Use them when the user's request matches their capabilities."
            ),
            llm_context=llm_context,
            tools=self._manager.get_tools(),
        )
