"""Entity cache with fuzzy name resolution for voice commands."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

REFRESH_INTERVAL = timedelta(seconds=60)
MATCH_THRESHOLD = 0.5


class EntityCache:
    """Cache of HA entity states with fuzzy name matching."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._entities: dict[str, State] = {}
        self._name_tokens: dict[str, set[str]] = {}
        self._token_index: dict[str, set[str]] = defaultdict(set)
        self._unsub_refresh: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Load entities and start periodic refresh."""
        try:
            await self.async_refresh()
        except Exception:
            _LOGGER.exception(
                "Initial entity cache refresh failed; cache will be empty "
                "until the next periodic refresh"
            )
        self._unsub_refresh = async_track_time_interval(
            self.hass, self._handle_refresh, REFRESH_INTERVAL
        )

    @callback
    def _handle_refresh(self, _now=None) -> None:
        """Handle the periodic refresh callback."""
        self.hass.async_create_task(self.async_refresh())

    async def async_refresh(self) -> None:
        """Reload all entity states from Home Assistant.

        On failure, the stale cache is preserved so callers can continue
        operating with slightly outdated data.
        """
        try:
            all_states = self.hass.states.async_all()
        except Exception:
            _LOGGER.exception(
                "Failed to fetch entity states from HA; keeping stale cache (%d entities)",
                len(self._entities),
            )
            return

        entities: dict[str, State] = {}
        name_tokens: dict[str, set[str]] = {}
        token_index: dict[str, set[str]] = defaultdict(set)

        for state in all_states:
            entities[state.entity_id] = state
            tokens = self._extract_tokens(state)
            name_tokens[state.entity_id] = tokens
            for token in tokens:
                token_index[token].add(state.entity_id)

        # Atomic swap — no window where callers see an empty cache
        self._entities = entities
        self._name_tokens = name_tokens
        self._token_index = token_index

        _LOGGER.debug("Entity cache refreshed: %d entities", len(self._entities))

    def _extract_tokens(self, state: State) -> set[str]:
        """Extract searchable tokens from an entity's friendly name and area."""
        tokens: set[str] = set()
        friendly_name = state.attributes.get("friendly_name", "")
        if friendly_name:
            tokens.update(friendly_name.lower().split())
        area = state.attributes.get("area_id", "")
        if area:
            tokens.update(area.lower().replace("_", " ").split())
        return tokens

    def resolve_name(self, spoken_name: str) -> str | None:
        """Fuzzy-match a spoken name to an entity_id using token overlap scoring.

        Returns the best match above the threshold, or None.
        """
        spoken_tokens = set(spoken_name.lower().split())
        if not spoken_tokens:
            return None

        best_id: str | None = None
        best_score: float = 0.0

        candidates: set[str] = set()
        for token in spoken_tokens:
            candidates.update(self._token_index.get(token, set()))

        if not candidates:
            candidates = set(self._entities)

        for entity_id in candidates:
            entity_tokens = self._name_tokens.get(entity_id, set())
            if not entity_tokens:
                continue
            overlap = len(spoken_tokens & entity_tokens)
            max_len = max(len(spoken_tokens), len(entity_tokens))
            score = overlap / max_len
            if score > best_score:
                best_score = score
                best_id = entity_id

        if best_score >= MATCH_THRESHOLD:
            return best_id
        return None

    def get_entity_state(self, entity_id: str) -> State | None:
        """Return the cached state for an entity_id."""
        return self._entities.get(entity_id)

    def get_entities_by_domain(self, domain: str) -> list[State]:
        """Return all cached states for a given domain."""
        prefix = f"{domain}."
        return [s for eid, s in self._entities.items() if eid.startswith(prefix)]

    def get_priority_snapshot(self, entity_ids: list[str]) -> str:
        """Return compact state summary for priority entities."""
        parts: list[str] = []
        for eid in entity_ids:
            eid = eid.strip()
            if not eid:
                continue
            state = self._entities.get(eid)
            if state is None:
                continue
            friendly = state.attributes.get("friendly_name", eid)
            val = state.state
            extras: list[str] = []
            if eid.startswith("light."):
                brightness = state.attributes.get("brightness")
                if brightness is not None:
                    extras.append(f"brightness:{brightness}")
            elif eid.startswith("climate."):
                temp = state.attributes.get("current_temperature") or state.attributes.get(
                    "temperature"
                )
                if temp is not None:
                    extras.append(f"temp:{temp}")
            elif eid.startswith("cover."):
                pos = state.attributes.get("current_position")
                if pos is not None:
                    extras.append(f"position:{pos}")

            detail = f"{friendly}={val}"
            if extras:
                detail += f"({', '.join(extras)})"
            parts.append(detail)

        if not parts:
            return ""
        return "Current entity states: " + ", ".join(parts)

    async def async_teardown(self) -> None:
        """Cancel the periodic refresh timer."""
        if self._unsub_refresh is not None:
            self._unsub_refresh()
            self._unsub_refresh = None
