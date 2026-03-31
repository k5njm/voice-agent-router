"""Pre-cached skill response system with cron-based refresh."""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant

    from .executor import SkillExecutor
    from .loader import SkillLoader

_LOGGER = logging.getLogger(__name__)

REFRESH_CHECK_INTERVAL = 60  # seconds between cron checks


@dataclass
class CachedResponse:
    """A cached skill response with TTL tracking."""

    response: str
    generated_at: float  # time.monotonic()
    ttl: int  # seconds


class SkillResponseCache:
    """In-memory cache for pre-generated skill responses."""

    def __init__(self) -> None:
        self._cache: dict[str, CachedResponse] = {}

    def get(self, skill_name: str) -> str | None:
        """Return cached response if within TTL, else None."""
        entry = self._cache.get(skill_name)
        if entry is None:
            return None
        if entry.ttl > 0 and time.monotonic() - entry.generated_at > entry.ttl:
            del self._cache[skill_name]
            return None
        return entry.response

    def put(self, skill_name: str, response: str, ttl: int) -> None:
        """Store a response in the cache."""
        self._cache[skill_name] = CachedResponse(
            response=response, generated_at=time.monotonic(), ttl=ttl
        )

    def invalidate(self, skill_name: str) -> None:
        """Remove a specific skill's cached response."""
        self._cache.pop(skill_name, None)

    def clear(self) -> None:
        """Remove all cached responses."""
        self._cache.clear()


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """Check if a datetime matches a 5-field cron expression.

    Supports: specific numbers, ``*`` (any), comma-separated lists,
    and ``*/N`` step values.  Fields are minute, hour, day-of-month,
    month, day-of-week (0=Monday .. 6=Sunday).
    """
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        _LOGGER.warning("Invalid cron expression (expected 5 fields): %s", cron_expr)
        return False

    time_values = [
        dt.minute,
        dt.hour,
        dt.day,
        dt.month,
        dt.weekday(),  # 0=Monday
    ]

    for field_expr, current in zip(fields, time_values, strict=True):
        if not _field_matches(field_expr, current):
            return False
    return True


def _field_matches(field_expr: str, value: int) -> bool:
    """Check if a single cron field matches a value."""
    if field_expr == "*":
        return True

    # Handle */N step syntax
    if field_expr.startswith("*/"):
        try:
            step = int(field_expr[2:])
            return step > 0 and value % step == 0
        except ValueError:
            return False

    # Handle comma-separated values
    for part in field_expr.split(","):
        part = part.strip()
        # Handle range syntax (e.g., 1-5)
        if "-" in part:
            try:
                low, high = part.split("-", 1)
                if int(low) <= value <= int(high):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                continue
    return False


class SkillCacheRefresher:
    """Periodically refreshes cached skill responses based on cron schedules."""

    def __init__(
        self,
        loader: SkillLoader,
        executor: SkillExecutor,
        cache: SkillResponseCache,
    ) -> None:
        self._loader = loader
        self._executor = executor
        self._cache = cache
        self._task: asyncio.Task | None = None
        self._unsub_state: object | None = None
        self._entity_skill_map: dict[str, set[str]] = {}

    async def start(self, hass: HomeAssistant) -> None:
        """Start the periodic cron check and entity-change listener."""
        self._hass = hass
        self._build_entity_skill_map()

        # Initial refresh for all cacheable skills
        await self._refresh_due_skills(force_all=True)

        # Start periodic loop
        self._task = asyncio.ensure_future(self._periodic_loop())

        # Listen for state changes to invalidate affected caches
        self._unsub_state = hass.bus.async_listen("state_changed", self._handle_state_change)

    async def stop(self) -> None:
        """Cancel the periodic refresh task and state listener."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None

    def _build_entity_skill_map(self) -> None:
        """Build a mapping from entity patterns to skill names."""
        self._entity_skill_map.clear()
        for skill in self._loader.skills.values():
            if skill.cache_cron is None:
                continue
            for pattern in skill.entities:
                skills_set = self._entity_skill_map.setdefault(pattern, set())
                skills_set.add(skill.name)

    def _handle_state_change(self, event: Event) -> None:
        """Invalidate cache entries when watched entities change."""
        entity_id = event.data.get("entity_id", "")
        for pattern, skill_names in self._entity_skill_map.items():
            if fnmatch.fnmatch(entity_id, pattern) or entity_id == pattern:
                for name in skill_names:
                    _LOGGER.debug(
                        "Invalidating cache for skill '%s' (entity %s changed)",
                        name,
                        entity_id,
                    )
                    self._cache.invalidate(name)

    async def _periodic_loop(self) -> None:
        """Run the cron check every REFRESH_CHECK_INTERVAL seconds."""
        while True:
            await asyncio.sleep(REFRESH_CHECK_INTERVAL)
            try:
                await self._refresh_due_skills()
            except Exception:
                _LOGGER.exception("Error during skill cache refresh")

    async def _refresh_due_skills(self, *, force_all: bool = False) -> None:
        """Refresh any skills whose cron schedule is currently due."""
        now = datetime.now()
        for skill in self._loader.skills.values():
            if skill.cache_cron is None or skill.requires_llm:
                continue
            if force_all or cron_matches(skill.cache_cron, now):
                try:
                    response = await self._executor.execute_template_skill(skill)
                    self._cache.put(skill.name, response, skill.cache_ttl)
                    _LOGGER.debug("Cached response for skill '%s'", skill.name)
                except Exception:
                    _LOGGER.exception("Failed to pre-cache skill '%s'", skill.name)
