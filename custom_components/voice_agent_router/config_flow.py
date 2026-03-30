"""Config flow for Voice Agent Router."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_API_KEY,
    CONF_ENABLE_LOCAL_ROUTER,
    CONF_MAX_TOOL_ITERATIONS,
    CONF_MODEL,
    CONF_SEND_BUG_REPORTS,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
        vol.Optional(CONF_SYSTEM_PROMPT, default=DEFAULT_SYSTEM_PROMPT): str,
        vol.Optional(CONF_TEMPERATURE, default=DEFAULT_TEMPERATURE): vol.Coerce(float),
        vol.Optional(CONF_MAX_TOOL_ITERATIONS, default=DEFAULT_MAX_TOOL_ITERATIONS): vol.Coerce(
            int
        ),
        vol.Optional(CONF_ENABLE_LOCAL_ROUTER, default=True): bool,
        vol.Optional(CONF_SEND_BUG_REPORTS, default=False): bool,
    }
)


class VoiceAgentRouterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voice Agent Router."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Voice Agent Router",
                data=user_input,
            )

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow."""
        return VoiceAgentRouterOptionsFlow(config_entry)


class VoiceAgentRouterOptionsFlow(OptionsFlow):
    """Handle options for Voice Agent Router."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MODEL,
                        default=current.get(CONF_MODEL, DEFAULT_MODEL),
                    ): str,
                    vol.Optional(
                        CONF_SYSTEM_PROMPT,
                        default=current.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
                    ): str,
                    vol.Optional(
                        CONF_TEMPERATURE,
                        default=current.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_MAX_TOOL_ITERATIONS,
                        default=current.get(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS),
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_ENABLE_LOCAL_ROUTER,
                        default=current.get(CONF_ENABLE_LOCAL_ROUTER, True),
                    ): bool,
                    vol.Optional(
                        CONF_SEND_BUG_REPORTS,
                        default=current.get(CONF_SEND_BUG_REPORTS, False),
                    ): bool,
                }
            ),
        )
