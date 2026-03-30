"""Tests for the EntityCache class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.voice_agent_router.entity_cache import EntityCache


@pytest.mark.asyncio
async def test_resolve_name_exact_match(entity_cache: EntityCache):
    """Exact friendly name should resolve to the correct entity_id."""
    result = entity_cache.resolve_name("Kitchen Lights")
    assert result == "light.kitchen_lights"


@pytest.mark.asyncio
async def test_resolve_name_partial_match(entity_cache: EntityCache):
    """A partial name like 'kitchen' should still resolve via token overlap."""
    result = entity_cache.resolve_name("kitchen")
    assert result == "light.kitchen_lights"


@pytest.mark.asyncio
async def test_resolve_name_below_threshold(entity_cache: EntityCache):
    """Random gibberish that shares no tokens should return None."""
    result = entity_cache.resolve_name("xyzzyplugh foobarbaz")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_name_empty_input(entity_cache: EntityCache):
    """Empty string should return None."""
    result = entity_cache.resolve_name("")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_name_multiple_candidates(entity_cache: EntityCache):
    """When multiple entities share tokens, the best scoring match wins."""
    # "Living Room Light" should match light.living_room, not other entities
    result = entity_cache.resolve_name("living room light")
    assert result == "light.living_room"


@pytest.mark.asyncio
async def test_get_entity_state(entity_cache: EntityCache):
    """get_entity_state returns state for valid entity, None for invalid."""
    state = entity_cache.get_entity_state("light.kitchen_lights")
    assert state is not None
    assert state.state == "off"

    missing = entity_cache.get_entity_state("light.nonexistent")
    assert missing is None


@pytest.mark.asyncio
async def test_get_entities_by_domain(entity_cache: EntityCache):
    """get_entities_by_domain filters correctly by domain prefix."""
    lights = entity_cache.get_entities_by_domain("light")
    assert len(lights) == 2
    light_ids = {s.entity_id for s in lights}
    assert "light.kitchen_lights" in light_ids
    assert "light.living_room" in light_ids

    sensors = entity_cache.get_entities_by_domain("sensor")
    assert len(sensors) == 1
    assert sensors[0].entity_id == "sensor.outdoor_temp"

    empty = entity_cache.get_entities_by_domain("fan")
    assert len(empty) == 0


@pytest.mark.asyncio
async def test_refresh_clears_and_reloads(mock_hass):
    """After refresh with new states, cache reflects the updated data."""
    cache = EntityCache(mock_hass)
    await cache.async_refresh()

    # Verify initial state
    assert cache.get_entity_state("light.kitchen_lights") is not None

    # Now change mock_hass to return a different set of states
    new_state = MagicMock()
    new_state.entity_id = "light.new_light"
    new_state.state = "on"
    new_state.attributes = {"friendly_name": "New Light"}
    mock_hass.states.async_all = MagicMock(return_value=[new_state])

    await cache.async_refresh()

    # Old entities should be gone
    assert cache.get_entity_state("light.kitchen_lights") is None
    # New entity should be present
    assert cache.get_entity_state("light.new_light") is not None
    assert cache.get_entity_state("light.new_light").state == "on"


@pytest.mark.asyncio
async def test_extract_tokens_with_area(mock_hass):
    """Entities with area_id should get area tokens indexed for matching."""
    # Create a state with an area_id attribute
    area_state = MagicMock()
    area_state.entity_id = "light.office_lamp"
    area_state.state = "off"
    area_state.attributes = {
        "friendly_name": "Lamp",
        "area_id": "home_office",
    }
    mock_hass.states.async_all = MagicMock(return_value=[area_state])

    cache = EntityCache(mock_hass)
    await cache.async_refresh()

    # Should resolve via area tokens ("home", "office") even though
    # friendly_name is just "Lamp"
    result = cache.resolve_name("office lamp")
    assert result == "light.office_lamp"

    # Should also resolve via area token alone if it scores high enough
    result = cache.resolve_name("home office lamp")
    assert result == "light.office_lamp"
