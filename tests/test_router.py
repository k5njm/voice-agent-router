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
