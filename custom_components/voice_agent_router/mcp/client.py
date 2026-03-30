"""Multi-server MCP client manager."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

_LOGGER = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    command: str
    args: list[str]
    env: dict[str, str] | None = None


class MCPClientManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._sessions: dict[str, Any] = {}  # name -> ClientSession
        self._transports: dict[str, Any] = {}  # name -> transport context
        self._tool_map: dict[str, tuple[str, Any]] = {}  # tool_name -> (server_name, tool_schema)

    async def async_start(self, server_configs: list[MCPServerConfig]) -> None:
        """Connect to all configured MCP servers and discover tools."""
        for config in server_configs:
            try:
                await self._connect_server(config)
            except Exception:
                _LOGGER.exception("Failed to connect MCP server: %s", config.name)

    async def _connect_server(self, config: MCPServerConfig) -> None:
        """Connect to a single MCP server via stdio transport."""
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env,
        )

        transport = None
        session = None
        try:
            transport = stdio_client(params)
            read_stream, write_stream = await transport.__aenter__()
            self._transports[config.name] = transport

            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            self._sessions[config.name] = session

            # Initialize and discover tools
            await session.initialize()
            tools_result = await session.list_tools()
        except FileNotFoundError:
            _LOGGER.error(
                "MCP server '%s' command not found: %s",
                config.name,
                config.command,
            )
            await self._cleanup_failed_server(config.name, session, transport)
            raise
        except OSError as err:
            _LOGGER.error(
                "Failed to spawn MCP server '%s' (command=%s): %s",
                config.name,
                config.command,
                err,
            )
            await self._cleanup_failed_server(config.name, session, transport)
            raise
        except Exception:
            _LOGGER.exception("Unexpected error connecting to MCP server '%s'", config.name)
            await self._cleanup_failed_server(config.name, session, transport)
            raise

        for tool in tools_result.tools:
            namespaced = f"mcp_{config.name}_{tool.name}"
            self._tool_map[namespaced] = (config.name, tool)
            _LOGGER.debug("Registered MCP tool: %s from %s", namespaced, config.name)

        _LOGGER.info(
            "Connected to MCP server '%s': %d tools",
            config.name,
            len(tools_result.tools),
        )

    async def _cleanup_failed_server(
        self, name: str, session: object | None, transport: object | None
    ) -> None:
        """Clean up partially-initialized server resources on connection failure."""
        if session is not None:
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                _LOGGER.debug("Error closing failed MCP session: %s", name)
            self._sessions.pop(name, None)
        if transport is not None:
            try:
                await transport.__aexit__(None, None, None)
            except Exception:
                _LOGGER.debug("Error closing failed MCP transport: %s", name)
            self._transports.pop(name, None)

    def get_tools(self) -> list[llm.Tool]:
        """Return all MCP tools wrapped as HA LLM Tool objects."""
        tools = []
        for namespaced_name, (server_name, tool_schema) in self._tool_map.items():
            tools.append(
                MCPTool(
                    manager=self,
                    namespaced_name=namespaced_name,
                    server_name=server_name,
                    mcp_tool=tool_schema,
                )
            )
        return tools

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """Execute a tool on the specified MCP server."""
        session = self._sessions.get(server_name)
        if session is None:
            _LOGGER.error(
                "MCP tool call failed: server '%s' not connected (tool=%s)",
                server_name,
                tool_name,
            )
            raise ValueError(f"MCP server '{server_name}' not connected")

        try:
            result = await session.call_tool(tool_name, arguments=args)
        except Exception:
            _LOGGER.exception(
                "MCP tool execution failed (server=%s, tool=%s)",
                server_name,
                tool_name,
            )
            raise

        # Extract text content from result
        try:
            if result.content:
                texts = [c.text for c in result.content if hasattr(c, "text")]
                return {"result": "\n".join(texts)} if texts else {"result": str(result.content)}
        except (AttributeError, TypeError):
            _LOGGER.warning(
                "Unexpected MCP result format from server '%s' tool '%s': %s",
                server_name,
                tool_name,
                type(result),
            )
            return {"result": str(result)}
        return {"result": "OK"}

    async def async_stop(self) -> None:
        """Disconnect all MCP servers."""
        for name, session in self._sessions.items():
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                _LOGGER.exception("Error closing MCP session: %s", name)

        for name, transport in self._transports.items():
            try:
                await transport.__aexit__(None, None, None)
            except Exception:
                _LOGGER.exception("Error closing MCP transport: %s", name)

        self._sessions.clear()
        self._transports.clear()
        self._tool_map.clear()


class MCPTool(llm.Tool):
    """An MCP tool wrapped as an HA LLM Tool."""

    def __init__(
        self,
        manager: MCPClientManager,
        namespaced_name: str,
        server_name: str,
        mcp_tool: Any,
    ) -> None:
        self.name = namespaced_name
        self.description = mcp_tool.description or ""
        self._manager = manager
        self._server_name = server_name
        self._original_name = mcp_tool.name
        # MCP tools define input_schema as JSON Schema; we store it for reference
        self._input_schema = getattr(mcp_tool, "inputSchema", {}) or {}

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the MCP tool."""
        try:
            return await self._manager.call_tool(
                self._server_name, self._original_name, tool_input.tool_args
            )
        except Exception as err:
            _LOGGER.exception("MCP tool call failed: %s", self.name)
            return {"error": str(err)}
