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
        await self.async_refresh()
        self._unsub_refresh = async_track_time_interval(
            self.hass, self._handle_refresh, REFRESH_INTERVAL
        )

    @callback
    def _handle_refresh(self, _now=None) -> None:
        """Handle the periodic refresh callback."""
        self.hass.async_create_task(self.async_refresh())

    async def async_refresh(self) -> None:
        """Reload all entity states from Home Assistant."""
        self._entities.clear()
        self._name_tokens.clear()
        self._token_index.clear()

        for state in self.hass.states.async_all():
            self._entities[state.entity_id] = state
            tokens = self._extract_tokens(state)
            self._name_tokens[state.entity_id] = tokens
            for token in tokens:
                self._token_index[token].add(state.entity_id)

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

    async def async_teardown(self) -> None:
        """Cancel the periodic refresh timer."""
        if self._unsub_refresh is not None:
            self._unsub_refresh()
            self._unsub_refresh = None
