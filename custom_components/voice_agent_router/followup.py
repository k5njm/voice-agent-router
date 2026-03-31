"""Follow-up conversation support for voice satellites.

After a voice response, automatically triggers the satellite to re-listen
so the user can issue follow-up commands without re-invoking the wake word.
Uses the HA assist_satellite.start_conversation service (HA 2025.4+).
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Phrases that signal the user is done with the conversation.
# Checked via substring match on the lowercased, stripped response text.
CONVERSATION_END_PHRASES: list[str] = [
    "that's all",
    "that is all",
    "thanks",
    "thank you",
    "stop",
    "never mind",
    "nevermind",
    "goodbye",
    "good bye",
    "done",
    "no thanks",
    "nope",
    "no thank you",
    "good night",
    "goodnight",
]


def is_conversation_end(text: str) -> bool:
    """Return True if the user's utterance signals end of conversation."""
    cleaned = text.strip().lower().rstrip(".!?,")
    # Exact match first (handles short phrases like "done", "stop", "nope")
    if cleaned in CONVERSATION_END_PHRASES:
        return True
    # Substring match for phrases embedded in longer text
    return any(phrase in cleaned for phrase in CONVERSATION_END_PHRASES)


class FollowupManager:
    """Triggers a voice satellite to re-listen after a response."""

    async def trigger_relisten(
        self,
        hass: HomeAssistant,
        satellite_id: str | None,
        device_id: str | None,
        timeout_seconds: float = 8.0,
    ) -> None:
        """Ask the satellite to start listening again.

        Uses assist_satellite.start_conversation which announces nothing
        and then listens for the next voice command.

        Parameters
        ----------
        hass: HomeAssistant instance
        satellite_id: entity_id of the assist_satellite (from ConversationInput.satellite_id)
        device_id: device_id fallback (from ConversationInput.device_id)
        timeout_seconds: how long to wait before giving up (not passed to the
            service — used as a local asyncio timeout guard)
        """
        entity_id = satellite_id or await self._resolve_satellite_entity(hass, device_id)
        if not entity_id:
            _LOGGER.debug("Cannot trigger follow-up: no satellite_id or device_id available")
            return

        # Small delay so the TTS response finishes playing before we re-listen
        await asyncio.sleep(0.5)

        try:
            async with asyncio.timeout(timeout_seconds):
                await hass.services.async_call(
                    "assist_satellite",
                    "start_conversation",
                    {"entity_id": entity_id},
                    blocking=True,
                )
            _LOGGER.debug("Follow-up re-listen triggered on %s", entity_id)
        except TimeoutError:
            _LOGGER.debug(
                "Follow-up re-listen timed out after %.1fs on %s",
                timeout_seconds,
                entity_id,
            )
        except Exception:
            _LOGGER.debug(
                "Follow-up re-listen failed on %s (service may not be available)",
                entity_id,
                exc_info=True,
            )

    @staticmethod
    async def _resolve_satellite_entity(hass: HomeAssistant, device_id: str | None) -> str | None:
        """Try to find an assist_satellite entity for the given device_id."""
        if not device_id:
            return None
        try:
            from homeassistant.helpers import entity_registry as er

            ent_reg = er.async_get(hass)
            entries = er.async_entries_for_device(ent_reg, device_id)
            for entry in entries:
                if entry.domain == "assist_satellite":
                    return entry.entity_id
        except Exception:
            _LOGGER.debug(
                "Could not resolve satellite entity for device %s",
                device_id,
                exc_info=True,
            )
        return None
