"""Tests for the MCP client manager."""

from __future__ import annotations

import pytest

from custom_components.voice_agent_router.mcp.client import MCPClientManager


@pytest.mark.asyncio
async def test_mcp_manager_init(mock_hass):
    manager = MCPClientManager(mock_hass)
    assert manager.get_tools() == []


@pytest.mark.asyncio
async def test_mcp_manager_stop_empty(mock_hass):
    manager = MCPClientManager(mock_hass)
    await manager.async_stop()  # Should not raise


@pytest.mark.asyncio
async def test_mcp_tool_call_no_server(mock_hass):
    manager = MCPClientManager(mock_hass)
    with pytest.raises(ValueError, match="not connected"):
        await manager.call_tool("nonexistent", "tool", {})
