"""Intent router — maps voice text to Home Assistant service calls."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..entity_cache import EntityCache
from .patterns import INTENT_PATTERNS

_LOGGER = logging.getLogger(__name__)


@dataclass
class LocalAction:
    """A fully-resolved HA service call ready for execution."""

    domain: str  # "light", "switch", "climate", "lock", "cover", "scene"
    service: str  # "turn_on", "turn_off", "set_temperature", etc.
    entity_id: str  # resolved from cache
    service_data: dict = field(default_factory=dict)
    speech: str = ""  # response text for TTS


class IntentRouter:
    """Try local regex patterns before falling back to an LLM."""

    def __init__(self, entity_cache: EntityCache) -> None:
        self._cache = entity_cache

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route(self, text: str) -> LocalAction | None:
        """Match *text* against known patterns and return a LocalAction.

        Returns ``None`` when no pattern matches or the spoken entity name
        cannot be resolved to a real entity_id.
        """
        cleaned = text.strip().lower()

        for pattern_name, regex, handler_name in INTENT_PATTERNS:
            match = regex.fullmatch(cleaned)
            if match is None:
                continue

            _LOGGER.debug("Pattern '%s' matched: %s", pattern_name, cleaned)

            handler = getattr(self, f"_{handler_name}", None)
            if handler is None:
                _LOGGER.warning("No handler '%s' for pattern '%s'", handler_name, pattern_name)
                continue

            action = handler(match, cleaned)
            if action is not None:
                return action

        return None

    # ------------------------------------------------------------------
    # Pattern handlers
    # ------------------------------------------------------------------

    def _handle_on_off(self, match: re.Match[str], text: str) -> LocalAction | None:
        entity_name = match.group("entity").strip()
        entity_id = self._cache.resolve_name(entity_name)
        if entity_id is None:
            return None

        domain = entity_id.split(".")[0]
        is_on = "on" in text.split() or text.startswith("turn on") or text.startswith("switch on")
        # Refine: check the captured group directly when using suffix form
        groups = match.groups()
        for g in groups:
            if g in ("on", "off"):
                is_on = g == "on"
                break

        service = "turn_on" if is_on else "turn_off"
        verb = "turning on" if is_on else "turning off"
        friendly = self._friendly(entity_id, entity_name)

        return LocalAction(
            domain=domain,
            service=service,
            entity_id=entity_id,
            speech=f"OK, {verb} the {friendly}.",
        )

    def _handle_brightness(self, match: re.Match[str], text: str) -> LocalAction | None:
        entity_name = match.group("entity").strip()
        value = int(match.group("value"))
        entity_id = self._cache.resolve_name(entity_name)
        if entity_id is None:
            return None

        friendly = self._friendly(entity_id, entity_name)
        return LocalAction(
            domain="light",
            service="turn_on",
            entity_id=entity_id,
            service_data={"brightness_pct": value},
            speech=f"OK, setting the {friendly} to {value} percent.",
        )

    def _handle_temperature(self, match: re.Match[str], text: str) -> LocalAction | None:
        value = int(match.group("value"))
        # Temperature commands typically target *the* thermostat; try to resolve
        entity_id = self._cache.resolve_name("thermostat")
        if entity_id is None:
            entity_id = self._cache.resolve_name("temperature")
        if entity_id is None:
            return None

        return LocalAction(
            domain="climate",
            service="set_temperature",
            entity_id=entity_id,
            service_data={"temperature": value},
            speech=f"OK, setting the thermostat to {value} degrees.",
        )

    def _handle_lock(self, match: re.Match[str], text: str) -> LocalAction | None:
        action = match.group("action").lower()
        entity_name = match.group("entity").strip()
        entity_id = self._cache.resolve_name(entity_name)
        if entity_id is None:
            return None

        service = "lock" if action == "lock" else "unlock"
        verb = "locking" if action == "lock" else "unlocking"
        friendly = self._friendly(entity_id, entity_name)

        return LocalAction(
            domain="lock",
            service=service,
            entity_id=entity_id,
            speech=f"OK, {verb} the {friendly}.",
        )

    def _handle_cover(self, match: re.Match[str], text: str) -> LocalAction | None:
        action = match.group("action").lower()
        entity_name = match.group("entity").strip()
        entity_id = self._cache.resolve_name(entity_name)
        if entity_id is None:
            return None

        service = "open_cover" if action == "open" else "close_cover"
        verb = "opening" if action == "open" else "closing"
        friendly = self._friendly(entity_id, entity_name)

        return LocalAction(
            domain="cover",
            service=service,
            entity_id=entity_id,
            speech=f"OK, {verb} the {friendly}.",
        )

    def _handle_scene(self, match: re.Match[str], text: str) -> LocalAction | None:
        scene_name = match.group("scene").strip()
        entity_id = self._cache.resolve_name(scene_name)
        if entity_id is None:
            # Try with "scene" appended for better matching
            entity_id = self._cache.resolve_name(f"{scene_name} scene")
        if entity_id is None:
            return None

        friendly = self._friendly(entity_id, scene_name)
        return LocalAction(
            domain="scene",
            service="turn_on",
            entity_id=entity_id,
            speech=f"OK, activating the {friendly} scene.",
        )

    def _handle_state_query(self, match: re.Match[str], text: str) -> LocalAction | None:
        entity_name = match.group("entity").strip()
        entity_id = self._cache.resolve_name(entity_name)
        if entity_id is None:
            return None

        state = self._cache.get_entity_state(entity_id)
        friendly = self._friendly(entity_id, entity_name)

        if state is None:
            speech = f"Sorry, I can't find the state of the {friendly}."
        else:
            unit = state.attributes.get("unit_of_measurement", "")
            speech = self._build_state_speech(friendly, state.state, unit)

        return LocalAction(
            domain="sensor",
            service="query",
            entity_id=entity_id,
            speech=speech,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _friendly(self, entity_id: str, fallback: str) -> str:
        """Return the entity's friendly name, falling back to the spoken name."""
        state = self._cache.get_entity_state(entity_id)
        if state is not None:
            name = state.attributes.get("friendly_name")
            if name:
                return name.lower()
        return fallback

    @staticmethod
    def _build_state_speech(friendly: str, state_value: str, unit: str) -> str:
        """Build a natural-language description of an entity's current state."""
        if unit:
            return f"The {friendly} is {state_value} {unit}."
        if state_value in ("on", "off", "open", "closed", "locked", "unlocked"):
            return f"The {friendly} is {state_value}."
        return f"The {friendly} is currently {state_value}."
