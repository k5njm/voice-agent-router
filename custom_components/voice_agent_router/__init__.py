"""Voice Agent Router integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SEND_BUG_REPORTS, DOMAIN, SENTRY_DSN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Agent Router from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    # Optional Sentry error reporting (off by default)
    send_reports = entry.options.get(CONF_SEND_BUG_REPORTS, False)
    if send_reports and SENTRY_DSN:
        try:

            def _init_sentry() -> None:
                import sentry_sdk

                def _before_send(event, hint):
                    """Only forward events that originate from this integration."""
                    for exc in event.get("exception", {}).get("values", []):
                        frames = exc.get("stacktrace", {}).get("frames", [])
                        if any("voice_agent_router" in (f.get("filename") or "") for f in frames):
                            return event
                    return None

                sentry_sdk.init(
                    dsn=SENTRY_DSN,
                    traces_sample_rate=0.0,
                    integrations=[],  # disable global hooks into aiohttp/asyncio/etc.
                    before_send=_before_send,
                )

            await hass.async_add_executor_job(_init_sentry)
            _LOGGER.info("Sentry error reporting enabled")
        except Exception:
            _LOGGER.exception("Failed to initialize Sentry")

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        _LOGGER.exception("Failed to set up platforms for Voice Agent Router")
        return False

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    except Exception:
        _LOGGER.exception("Error unloading Voice Agent Router platforms")
        return False

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    try:
        await hass.config_entries.async_reload(entry.entry_id)
    except Exception:
        _LOGGER.exception(
            "Failed to reload Voice Agent Router after options update (entry=%s)",
            entry.entry_id,
        )
