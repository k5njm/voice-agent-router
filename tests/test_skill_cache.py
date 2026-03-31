"""Tests for the skill response cache system."""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.voice_agent_router.skills.cache import (
    SkillCacheRefresher,
    SkillResponseCache,
    cron_matches,
)
from custom_components.voice_agent_router.skills.loader import SkillDefinition

# ---------------------------------------------------------------------------
# SkillResponseCache tests
# ---------------------------------------------------------------------------


class TestSkillResponseCache:
    def test_get_empty_returns_none(self):
        cache = SkillResponseCache()
        assert cache.get("nonexistent") is None

    def test_put_then_get(self):
        cache = SkillResponseCache()
        cache.put("greeting", "Good morning!", ttl=300)
        assert cache.get("greeting") == "Good morning!"

    def test_ttl_expiry(self):
        cache = SkillResponseCache()
        cache.put("greeting", "Good morning!", ttl=10)

        # Patch the generated_at to simulate time passing
        cache._cache["greeting"].generated_at = time.monotonic() - 11
        assert cache.get("greeting") is None

    def test_ttl_not_expired(self):
        cache = SkillResponseCache()
        cache.put("greeting", "Good morning!", ttl=300)
        assert cache.get("greeting") == "Good morning!"

    def test_invalidate_removes_entry(self):
        cache = SkillResponseCache()
        cache.put("greeting", "Good morning!", ttl=300)
        cache.invalidate("greeting")
        assert cache.get("greeting") is None

    def test_invalidate_nonexistent_is_noop(self):
        cache = SkillResponseCache()
        cache.invalidate("nonexistent")  # should not raise

    def test_clear_removes_all(self):
        cache = SkillResponseCache()
        cache.put("a", "response a", ttl=300)
        cache.put("b", "response b", ttl=300)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_zero_ttl_never_expires(self):
        """TTL of 0 means the entry never expires based on time."""
        cache = SkillResponseCache()
        cache.put("forever", "I last forever", ttl=0)
        # Even after simulating time passage, ttl=0 means no expiry
        cache._cache["forever"].generated_at = time.monotonic() - 999999
        assert cache.get("forever") == "I last forever"


# ---------------------------------------------------------------------------
# Cron matching tests
# ---------------------------------------------------------------------------


class TestCronMatches:
    def test_every_minute(self):
        dt = datetime(2026, 3, 30, 10, 15)
        assert cron_matches("* * * * *", dt) is True

    def test_specific_minute(self):
        dt = datetime(2026, 3, 30, 10, 15)
        assert cron_matches("15 * * * *", dt) is True
        assert cron_matches("30 * * * *", dt) is False

    def test_specific_hour(self):
        dt = datetime(2026, 3, 30, 10, 0)
        assert cron_matches("0 10 * * *", dt) is True
        assert cron_matches("0 11 * * *", dt) is False

    def test_every_15_minutes(self):
        assert cron_matches("*/15 * * * *", datetime(2026, 3, 30, 10, 0)) is True
        assert cron_matches("*/15 * * * *", datetime(2026, 3, 30, 10, 15)) is True
        assert cron_matches("*/15 * * * *", datetime(2026, 3, 30, 10, 30)) is True
        assert cron_matches("*/15 * * * *", datetime(2026, 3, 30, 10, 7)) is False

    def test_comma_separated(self):
        dt = datetime(2026, 3, 30, 10, 15)
        assert cron_matches("0,15,30,45 * * * *", dt) is True
        assert cron_matches("0,30,45 * * * *", dt) is False

    def test_range(self):
        dt = datetime(2026, 3, 30, 10, 15)
        assert cron_matches("10-20 * * * *", dt) is True
        assert cron_matches("20-30 * * * *", dt) is False

    def test_specific_day_of_week(self):
        # 2026-03-30 is a Monday (weekday()=0)
        dt = datetime(2026, 3, 30, 10, 0)
        assert cron_matches("0 10 * * 0", dt) is True  # Monday
        assert cron_matches("0 10 * * 1", dt) is False  # Tuesday

    def test_invalid_cron_expression(self):
        dt = datetime(2026, 3, 30, 10, 0)
        assert cron_matches("bad cron", dt) is False

    def test_month_field(self):
        dt = datetime(2026, 3, 30, 10, 0)
        assert cron_matches("0 10 * 3 *", dt) is True
        assert cron_matches("0 10 * 6 *", dt) is False

    def test_day_of_month(self):
        dt = datetime(2026, 3, 30, 10, 0)
        assert cron_matches("0 10 30 * *", dt) is True
        assert cron_matches("0 10 15 * *", dt) is False


# ---------------------------------------------------------------------------
# Cache integration with executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_skips_template_execution():
    """When a response is cached, the executor should return it without rendering."""
    from custom_components.voice_agent_router.skills.executor import SkillExecutor

    cache = SkillResponseCache()
    cache.put("good_morning", "Cached morning!", ttl=300)

    hass = MagicMock()
    entity_cache = MagicMock()
    executor = SkillExecutor(hass, entity_cache, response_cache=cache)

    skill = SkillDefinition(
        name="good_morning",
        description="Morning briefing",
        trigger_patterns=["good morning"],
        response_template="This should not render",
        entities=["sensor.outdoor_temp"],
        cache_cron="0 6 * * *",
        cache_ttl=3600,
    )

    result = await executor.execute_template_skill(skill)
    assert result == "Cached morning!"
    # Template was never rendered - entity_cache was never accessed
    entity_cache.get_entity_state.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_falls_through():
    """When cache is empty, the executor should render the template."""
    import sys

    from custom_components.voice_agent_router.skills.executor import SkillExecutor

    cache = SkillResponseCache()

    hass = MagicMock()
    entity_cache = MagicMock()
    entity_cache.get_entity_state.return_value = None

    # Mock Template on the HA stub so the lazy import inside execute_template_skill works
    mock_template_instance = MagicMock()
    mock_template_instance.async_render.return_value = "Rendered response"
    mock_template_cls = MagicMock(return_value=mock_template_instance)
    sys.modules["homeassistant.helpers.template"].Template = mock_template_cls

    executor = SkillExecutor(hass, entity_cache, response_cache=cache)

    skill = SkillDefinition(
        name="good_morning",
        description="Morning briefing",
        trigger_patterns=["good morning"],
        response_template="Hello {{ states }}",
        entities=["sensor.outdoor_temp"],
        cache_cron="0 6 * * *",
        cache_ttl=3600,
    )

    result = await executor.execute_template_skill(skill)

    assert result == "Rendered response"
    # The result should now be cached
    assert cache.get("good_morning") == "Rendered response"


# ---------------------------------------------------------------------------
# Entity change invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entity_change_invalidates_cache():
    """State changes for watched entities should invalidate the skill cache."""
    cache = SkillResponseCache()
    cache.put("good_morning", "Cached morning!", ttl=3600)

    skill = SkillDefinition(
        name="good_morning",
        description="Morning briefing",
        trigger_patterns=["good morning"],
        response_template="Hello",
        entities=["sensor.outdoor_temp", "weather.home"],
        cache_cron="0 6 * * *",
        cache_ttl=3600,
    )

    loader = MagicMock()
    loader.skills = {"good_morning": skill}

    executor = MagicMock()
    refresher = SkillCacheRefresher(loader, executor, cache)

    # Simulate start (build entity map without starting the async loop)
    refresher._build_entity_skill_map()

    # Simulate a state change event for a watched entity
    event = MagicMock()
    event.data = {"entity_id": "sensor.outdoor_temp"}
    refresher._handle_state_change(event)

    # Cache should be invalidated
    assert cache.get("good_morning") is None


@pytest.mark.asyncio
async def test_entity_glob_pattern_invalidation():
    """Glob patterns in entities should match and invalidate."""
    cache = SkillResponseCache()
    cache.put("doors_check", "All doors closed", ttl=3600)

    skill = SkillDefinition(
        name="doors_check",
        description="Door status",
        trigger_patterns=["check doors"],
        response_template="Doors status",
        entities=["binary_sensor.*_door*"],
        cache_cron="*/5 * * * *",
        cache_ttl=600,
    )

    loader = MagicMock()
    loader.skills = {"doors_check": skill}

    executor = MagicMock()
    refresher = SkillCacheRefresher(loader, executor, cache)
    refresher._build_entity_skill_map()

    event = MagicMock()
    event.data = {"entity_id": "binary_sensor.front_door_contact"}
    refresher._handle_state_change(event)

    assert cache.get("doors_check") is None


@pytest.mark.asyncio
async def test_unrelated_entity_change_preserves_cache():
    """State changes for unrelated entities should not invalidate."""
    cache = SkillResponseCache()
    cache.put("good_morning", "Cached morning!", ttl=3600)

    skill = SkillDefinition(
        name="good_morning",
        description="Morning briefing",
        trigger_patterns=["good morning"],
        response_template="Hello",
        entities=["sensor.outdoor_temp"],
        cache_cron="0 6 * * *",
        cache_ttl=3600,
    )

    loader = MagicMock()
    loader.skills = {"good_morning": skill}

    executor = MagicMock()
    refresher = SkillCacheRefresher(loader, executor, cache)
    refresher._build_entity_skill_map()

    event = MagicMock()
    event.data = {"entity_id": "light.kitchen"}
    refresher._handle_state_change(event)

    # Cache should still be valid
    assert cache.get("good_morning") == "Cached morning!"


# ---------------------------------------------------------------------------
# Loader parses cache block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loader_parses_cache_block(tmp_path):
    from custom_components.voice_agent_router.skills.loader import SkillLoader

    skill_file = tmp_path / "cached_skill.yaml"
    skill_file.write_text("""
name: good_morning
description: "Morning briefing"
trigger:
  patterns: ["good morning"]
requires_llm: false
response_template: "Good morning!"
entities:
  - sensor.outdoor_temp
cache:
  cron: "0 6 * * *"
  ttl: 3600
""")

    loader = SkillLoader(tmp_path)
    await loader.async_load()

    skill = loader.skills["good_morning"]
    assert skill.cache_cron == "0 6 * * *"
    assert skill.cache_ttl == 3600


@pytest.mark.asyncio
async def test_loader_no_cache_block(tmp_path):
    from custom_components.voice_agent_router.skills.loader import SkillLoader

    skill_file = tmp_path / "simple_skill.yaml"
    skill_file.write_text("""
name: simple
description: "Simple skill"
trigger:
  patterns: ["do thing"]
requires_llm: false
response_template: "Done!"
""")

    loader = SkillLoader(tmp_path)
    await loader.async_load()

    skill = loader.skills["simple"]
    assert skill.cache_cron is None
    assert skill.cache_ttl == 0


# ---------------------------------------------------------------------------
# Refresh due skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_due_skills_caches_response():
    """When force_all=True, all cacheable skills get pre-cached."""
    cache = SkillResponseCache()

    skill = SkillDefinition(
        name="good_morning",
        description="Morning briefing",
        trigger_patterns=["good morning"],
        response_template="Good morning!",
        entities=["sensor.outdoor_temp"],
        cache_cron="0 6 * * *",
        cache_ttl=3600,
    )

    loader = MagicMock()
    loader.skills = {"good_morning": skill}

    executor = MagicMock()
    executor.execute_template_skill = AsyncMock(return_value="Pre-cached morning!")

    refresher = SkillCacheRefresher(loader, executor, cache)
    await refresher._refresh_due_skills(force_all=True)

    assert cache.get("good_morning") == "Pre-cached morning!"
    executor.execute_template_skill.assert_called_once_with(skill)
