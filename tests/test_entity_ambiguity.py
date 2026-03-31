"""Tests for entity ambiguity resolution: group preference, domain hints, aliases."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.voice_agent_router.entity_aliases import EntityAliasLoader
from custom_components.voice_agent_router.entity_cache import EntityCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(entity_id: str, friendly_name: str, state: str = "off", attrs=None):
    """Create a mock HA State object."""
    mock = MagicMock()
    mock.entity_id = entity_id
    mock.state = state
    mock.attributes = {"friendly_name": friendly_name, **(attrs or {})}
    return mock


def _make_hass(states):
    """Create a mock hass with the given list of state objects."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=states)
    hass.async_create_task = MagicMock()
    return hass


# ---------------------------------------------------------------------------
# Group preference tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_preferred_over_member():
    """When a group and its member have similar names, the group should win."""
    states = [
        _make_state(
            "light.bedroom_lamps",
            "Bedroom Lamps",
            attrs={"entity_id": ["light.bedroom_lamp_1", "light.bedroom_lamp_2"]},
        ),
        _make_state("light.bedroom_lamp_1", "Bedroom Lamp 1"),
        _make_state("light.bedroom_lamp_2", "Bedroom Lamp 2"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass)
    await cache.async_refresh()

    result = cache.resolve_name("bedroom lamps")
    assert result == "light.bedroom_lamps"


@pytest.mark.asyncio
async def test_group_domain_prefix():
    """Entities in the group.* domain should be detected as groups."""
    states = [
        _make_state("group.living_room_lights", "Living Room Lights"),
        _make_state("light.living_room_lamp", "Living Room Lamp"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass)
    await cache.async_refresh()

    result = cache.resolve_name("living room lights")
    assert result == "group.living_room_lights"


@pytest.mark.asyncio
async def test_group_suffix_pattern():
    """Entities ending with _group should be detected as groups."""
    states = [
        _make_state("light.kitchen_group", "Kitchen Lights"),
        _make_state("light.kitchen_counter", "Kitchen Counter Light"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass)
    await cache.async_refresh()

    result = cache.resolve_name("kitchen lights")
    assert result == "light.kitchen_group"


# ---------------------------------------------------------------------------
# Domain hint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_hint_light():
    """'lamps' in the spoken name should favour light domain entities."""
    states = [
        _make_state("light.bedroom_lamps", "Bedroom Lamps"),
        _make_state("switch.bedroom_lamps", "Bedroom Lamps Switch"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass)
    await cache.async_refresh()

    result = cache.resolve_name("bedroom lamps")
    assert result == "light.bedroom_lamps"


@pytest.mark.asyncio
async def test_domain_hint_cover():
    """'blinds' in the spoken name should favour cover domain entities."""
    states = [
        _make_state("cover.bedroom_blinds", "Bedroom Blinds"),
        _make_state("switch.bedroom_blinds", "Bedroom Blinds Switch"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass)
    await cache.async_refresh()

    result = cache.resolve_name("bedroom blinds")
    assert result == "cover.bedroom_blinds"


@pytest.mark.asyncio
async def test_domain_hint_climate():
    """'thermostat' in the spoken name should favour climate domain."""
    states = [
        _make_state("climate.living_room", "Living Room Thermostat"),
        _make_state("sensor.living_room_temp", "Living Room Temperature"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass)
    await cache.async_refresh()

    result = cache.resolve_name("living room thermostat")
    assert result == "climate.living_room"


# ---------------------------------------------------------------------------
# Alias tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alias_exact_match(tmp_path):
    """Alias match should bypass fuzzy scoring and return the entity_id directly."""
    alias_file = tmp_path / "entity_aliases.yaml"
    alias_file.write_text(
        "aliases:\n  light.bedroom_lamp_group:\n    - bedroom lamps\n    - bedside lamps\n"
    )
    loader = EntityAliasLoader(tmp_path)

    states = [
        _make_state("light.bedroom_lamp_group", "Bedroom Lamp Group"),
        _make_state("light.bedroom_lamp_1", "Bedroom Lamp 1"),
    ]
    hass = _make_hass(states)
    cache = EntityCache(hass, alias_loader=loader)
    await cache.async_refresh()

    assert cache.resolve_name("bedroom lamps") == "light.bedroom_lamp_group"
    assert cache.resolve_name("bedside lamps") == "light.bedroom_lamp_group"


@pytest.mark.asyncio
async def test_alias_case_insensitive(tmp_path):
    """Alias matching should be case-insensitive."""
    alias_file = tmp_path / "entity_aliases.yaml"
    alias_file.write_text("aliases:\n  light.den:\n    - Den Lights\n")
    loader = EntityAliasLoader(tmp_path)
    assert loader.resolve_alias("den lights") == "light.den"
    assert loader.resolve_alias("DEN LIGHTS") == "light.den"


def test_alias_no_file(tmp_path):
    """Missing alias file should not raise; resolve_alias returns None."""
    loader = EntityAliasLoader(tmp_path)
    assert loader.resolve_alias("anything") is None


def test_alias_empty_file(tmp_path):
    """Empty alias file should not raise."""
    (tmp_path / "entity_aliases.yaml").write_text("")
    loader = EntityAliasLoader(tmp_path)
    assert loader.resolve_alias("anything") is None


# ---------------------------------------------------------------------------
# Regression: existing resolve_name behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_exact_match_still_works(entity_cache: EntityCache):
    """Exact friendly name should still resolve correctly (no regression)."""
    assert entity_cache.resolve_name("Kitchen Lights") == "light.kitchen_lights"


@pytest.mark.asyncio
async def test_resolve_partial_match_still_works(entity_cache: EntityCache):
    """Partial token match should still resolve (no regression)."""
    result = entity_cache.resolve_name("kitchen")
    assert result == "light.kitchen_lights"


@pytest.mark.asyncio
async def test_resolve_no_match_still_returns_none(entity_cache: EntityCache):
    """Unrecognised spoken name should still return None."""
    assert entity_cache.resolve_name("xyzzyplugh foobarbaz") is None
