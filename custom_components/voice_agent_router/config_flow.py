"""Config flow for Voice Agent Router."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import (
    CONF_API_KEY,
    CONF_ENABLE_LOCAL_ROUTER,
    CONF_MAX_TOOL_ITERATIONS,
    CONF_MODEL,
    CONF_SYSTEM_PROMPT,
    CONF_SYSTEM_PROMPT_PRESET,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
    PRESET_CUSTOM,
    PRESET_DEFAULT,
    SYSTEM_PROMPT_PRESETS,
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
        vol.Optional(CONF_MAX_TOOL_ITERATIONS, default=DEFAULT_MAX_TOOL_ITERATIONS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional(CONF_ENABLE_LOCAL_ROUTER, default=True): bool,
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
        return VoiceAgentRouterOptionsFlow()


class VoiceAgentRouterOptionsFlow(OptionsFlow):
    """Handle options for Voice Agent Router."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        data = self.config_entry.data

        def opt(key, default):
            return current.get(key, data.get(key, default))

        preset_options = [
            {"value": k, "label": k.capitalize()} for k in [*SYSTEM_PROMPT_PRESETS, PRESET_CUSTOM]
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_MODEL, default=opt(CONF_MODEL, DEFAULT_MODEL)): str,
                    vol.Optional(
                        CONF_SYSTEM_PROMPT_PRESET,
                        default=opt(CONF_SYSTEM_PROMPT_PRESET, PRESET_DEFAULT),
                    ): SelectSelector(SelectSelectorConfig(options=preset_options)),
                    vol.Optional(
                        CONF_SYSTEM_PROMPT,
                        default=opt(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
                    ): str,
                    vol.Optional(
                        CONF_TEMPERATURE, default=opt(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_MAX_TOOL_ITERATIONS,
                        default=opt(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                    vol.Optional(
                        CONF_ENABLE_LOCAL_ROUTER, default=opt(CONF_ENABLE_LOCAL_ROUTER, True)
                    ): bool,
                }
            ),
        )
