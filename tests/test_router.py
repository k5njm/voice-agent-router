"""Tests for the intent router."""

from __future__ import annotations

import pytest

from custom_components.voice_agent_router.router.intent_router import IntentRouter


@pytest.mark.asyncio
async def test_turn_on_light(intent_router: IntentRouter):
    action = await intent_router.route("turn on the kitchen lights")
    assert action is not None
    assert action.domain == "light"
    assert action.service == "turn_on"
    assert action.entity_id == "light.kitchen_lights"
    assert "turning on" in action.speech.lower()


@pytest.mark.asyncio
async def test_turn_off_switch(intent_router: IntentRouter):
    action = await intent_router.route("turn off the garage door switch")
    assert action is not None
    assert action.service == "turn_off"


@pytest.mark.asyncio
async def test_set_brightness(intent_router: IntentRouter):
    action = await intent_router.route("set the living room light to 50 percent")
    assert action is not None
    assert action.domain == "light"
    assert action.service == "turn_on"
    assert action.service_data.get("brightness_pct") == 50


@pytest.mark.asyncio
async def test_set_temperature(intent_router: IntentRouter):
    action = await intent_router.route("set the thermostat to 72 degrees")
    assert action is not None
    assert action.domain == "climate"
    assert action.service == "set_temperature"
    assert action.service_data.get("temperature") == 72


@pytest.mark.asyncio
async def test_lock_door(intent_router: IntentRouter):
    action = await intent_router.route("lock the front door")
    assert action is not None
    assert action.domain == "lock"
    assert action.service == "lock"


@pytest.mark.asyncio
async def test_unlock_door(intent_router: IntentRouter):
    action = await intent_router.route("unlock the front door")
    assert action is not None
    assert action.service == "unlock"


@pytest.mark.asyncio
async def test_open_cover(intent_router: IntentRouter):
    action = await intent_router.route("open the bedroom blinds")
    assert action is not None
    assert action.domain == "cover"
    assert action.service == "open_cover"


@pytest.mark.asyncio
async def test_close_cover(intent_router: IntentRouter):
    action = await intent_router.route("close the bedroom blinds")
    assert action is not None
    assert action.service == "close_cover"


@pytest.mark.asyncio
async def test_activate_scene(intent_router: IntentRouter):
    action = await intent_router.route("activate the movie night scene")
    assert action is not None
    assert action.domain == "scene"
    assert action.service == "turn_on"


@pytest.mark.asyncio
async def test_state_query(intent_router: IntentRouter):
    action = await intent_router.route("what is the outdoor temperature")
    assert action is not None
    assert action.service == "query"
    assert "65" in action.speech


@pytest.mark.asyncio
async def test_no_match(intent_router: IntentRouter):
    action = await intent_router.route("tell me a joke")
    assert action is None


@pytest.mark.asyncio
async def test_unresolvable_entity(intent_router: IntentRouter):
    action = await intent_router.route("turn on the nonexistent device xyz123")
    assert action is None


# --- Edge-case tests -------------------------------------------------------


@pytest.mark.asyncio
async def test_case_insensitive(intent_router: IntentRouter):
    """ALL-CAPS input should still match."""
    action = await intent_router.route("TURN ON THE KITCHEN LIGHTS")
    assert action is not None
    assert action.domain == "light"
    assert action.service == "turn_on"
    assert action.entity_id == "light.kitchen_lights"


@pytest.mark.asyncio
async def test_suffix_form_on(intent_router: IntentRouter):
    """'kitchen lights on' (ON_OFF_SUFFIX pattern) should work."""
    action = await intent_router.route("kitchen lights on")
    assert action is not None
    assert action.service == "turn_on"
    assert action.entity_id == "light.kitchen_lights"


@pytest.mark.asyncio
async def test_suffix_form_off(intent_router: IntentRouter):
    """'living room light off' (ON_OFF_SUFFIX pattern) should work."""
    action = await intent_router.route("living room light off")
    assert action is not None
    assert action.service == "turn_off"
    assert action.entity_id == "light.living_room"


@pytest.mark.asyncio
async def test_extra_whitespace(intent_router: IntentRouter):
    """Leading/trailing/extra whitespace should be tolerated."""
    action = await intent_router.route("  turn on  the  kitchen lights  ")
    assert action is not None
    assert action.entity_id == "light.kitchen_lights"
    assert action.service == "turn_on"


@pytest.mark.asyncio
async def test_dim_light(intent_router: IntentRouter):
    """'dim the living room light to 30 percent' should set brightness."""
    action = await intent_router.route("dim the living room light to 30 percent")
    assert action is not None
    assert action.domain == "light"
    assert action.service == "turn_on"
    assert action.service_data.get("brightness_pct") == 30
    assert action.entity_id == "light.living_room"


@pytest.mark.asyncio
async def test_close_cover_with_entity_id(intent_router: IntentRouter):
    """'close the bedroom blinds' should resolve to cover.close_cover with correct entity."""
    action = await intent_router.route("close the bedroom blinds")
    assert action is not None
    assert action.domain == "cover"
    assert action.service == "close_cover"
    assert action.entity_id == "cover.bedroom_blinds"


@pytest.mark.asyncio
async def test_state_query_with_unit(intent_router: IntentRouter):
    """State query for a sensor with unit_of_measurement includes the unit."""
    action = await intent_router.route("what is the outdoor temperature")
    assert action is not None
    assert action.service == "query"
    assert "65" in action.speech
    assert "\u00b0F" in action.speech


@pytest.mark.asyncio
async def test_state_query_binary(intent_router: IntentRouter):
    """'is the back door open' should return a state query for binary_sensor."""
    action = await intent_router.route("is the back door open")
    assert action is not None
    assert action.service == "query"
    assert action.entity_id == "binary_sensor.back_door"
    # The binary_sensor state is "on", so speech should contain "on"
    assert "on" in action.speech
