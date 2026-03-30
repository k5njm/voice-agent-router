"""Test fixtures for Voice Agent Router."""

from __future__ import annotations

# Must be first — stubs out HA and heavy deps before any custom_component import.
from tests import ha_stubs

ha_stubs.install()

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

from custom_components.voice_agent_router.entity_cache import EntityCache  # noqa: E402
from custom_components.voice_agent_router.router.intent_router import IntentRouter  # noqa: E402


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.async_create_task = MagicMock()

    states = []
    for entity_id, friendly_name, state_val, attrs in [
        ("light.kitchen_lights", "Kitchen Lights", "off", {}),
        ("light.living_room", "Living Room Light", "on", {"brightness": 200}),
        ("switch.garage_door", "Garage Door Switch", "off", {}),
        (
            "climate.downstairs",
            "Downstairs Thermostat",
            "heat",
            {
                "current_temperature": 72,
                "temperature": 70,
                "unit_of_measurement": "°F",
            },
        ),
        ("lock.front_door", "Front Door Lock", "locked", {}),
        ("cover.bedroom_blinds", "Bedroom Blinds", "open", {}),
        ("scene.movie_night", "Movie Night", "scening", {}),
        (
            "sensor.outdoor_temp",
            "Outdoor Temperature",
            "65",
            {"unit_of_measurement": "°F"},
        ),
        ("binary_sensor.back_door", "Back Door", "on", {}),
    ]:
        mock_state = MagicMock()
        mock_state.entity_id = entity_id
        mock_state.state = state_val
        mock_state.attributes = {"friendly_name": friendly_name, **attrs}
        states.append(mock_state)

    hass.states.async_all = MagicMock(return_value=states)
    return hass


@pytest.fixture
async def entity_cache(mock_hass):
    """Create and set up an entity cache with mock data."""
    cache = EntityCache(mock_hass)
    await cache.async_refresh()
    return cache


@pytest.fixture
def intent_router(entity_cache):
    """Create an intent router with the entity cache."""
    return IntentRouter(entity_cache)


@pytest.fixture
def skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    skill1 = tmp_path / "test_skill.yaml"
    skill1.write_text("""
name: test_skill
description: "A test skill"
trigger:
  patterns: ["test me", "run test"]
requires_llm: false
response_template: "Test skill executed successfully."
entities: []
""")

    skill2 = tmp_path / "llm_skill.yaml"
    skill2.write_text("""
name: llm_skill
description: "An LLM-backed test skill"
trigger:
  patterns: ["smart test"]
requires_llm: true
system_prompt: "You are testing."
tools: [ha_get_state]
""")

    return tmp_path
