"""Tests for the ActionCache."""

from __future__ import annotations

import time

from custom_components.voice_agent_router.action_cache import ActionCache

# ---------------------------------------------------------------------------
# Basic record / retrieval
# ---------------------------------------------------------------------------


def test_record_and_get_recent():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    recent = cache.get_recent()
    assert len(recent) == 1
    assert recent[0].entity_id == "light.kitchen"
    assert recent[0].domain == "light"
    assert recent[0].service == "turn_on"
    assert recent[0].friendly_name == "Kitchen Lights"


def test_get_recent_returns_newest_first():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")
    recent = cache.get_recent()
    assert len(recent) == 2
    assert recent[0].entity_id == "switch.garage"
    assert recent[1].entity_id == "light.kitchen"


def test_empty_cache_returns_empty():
    cache = ActionCache()
    assert cache.get_recent() == []
    assert cache.get_last_entity() is None
    assert cache.resolve_reference("that light") is None
    assert cache.format_context() == ""


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


def test_ttl_expiry():
    cache = ActionCache(max_age=1.0)
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")

    # Patch the timestamp to simulate passage of time
    cache._history[0].timestamp = time.monotonic() - 2.0

    assert cache.get_recent() == []
    assert cache.get_last_entity() is None


def test_ttl_mixed_fresh_and_stale():
    cache = ActionCache(max_age=5.0)
    cache.record("light.old", "light", "turn_on", "Old Light")
    cache._history[0].timestamp = time.monotonic() - 10.0

    cache.record("light.new", "light", "turn_on", "New Light")

    recent = cache.get_recent()
    assert len(recent) == 1
    assert recent[0].entity_id == "light.new"


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def test_lru_eviction():
    cache = ActionCache(max_size=3)
    for i in range(5):
        cache.record(f"light.item_{i}", "light", "turn_on", f"Item {i}")

    # Only 3 most recent should remain
    recent = cache.get_recent()
    assert len(recent) == 3
    ids = [r.entity_id for r in recent]
    assert "light.item_2" in ids
    assert "light.item_3" in ids
    assert "light.item_4" in ids
    assert "light.item_0" not in ids
    assert "light.item_1" not in ids


# ---------------------------------------------------------------------------
# get_last_entity
# ---------------------------------------------------------------------------


def test_get_last_entity_no_domain_filter():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")

    last = cache.get_last_entity()
    assert last is not None
    assert last.entity_id == "switch.garage"


def test_get_last_entity_with_domain_filter():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")

    last = cache.get_last_entity(domain="light")
    assert last is not None
    assert last.entity_id == "light.kitchen"


def test_get_last_entity_no_matching_domain():
    cache = ActionCache()
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")

    assert cache.get_last_entity(domain="light") is None


# ---------------------------------------------------------------------------
# resolve_reference
# ---------------------------------------------------------------------------


def test_resolve_that_light():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    assert cache.resolve_reference("turn off that light") == "light.kitchen"


def test_resolve_that_one():
    cache = ActionCache()
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")
    assert cache.resolve_reference("turn on that one") == "switch.garage"


def test_resolve_it():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    assert cache.resolve_reference("turn it off") == "light.kitchen"


def test_resolve_the_same_light():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    assert cache.resolve_reference("set the same light to 50") == "light.kitchen"


def test_resolve_the_same_one():
    cache = ActionCache()
    cache.record("light.bedroom", "light", "turn_on", "Bedroom Light")
    assert cache.resolve_reference("turn off the same one") == "light.bedroom"


def test_resolve_no_pronoun():
    """Normal entity names should not trigger pronoun resolution."""
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    assert cache.resolve_reference("turn on kitchen lights") is None


def test_resolve_domain_filtered():
    """'that light' should return last light, not last switch."""
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")

    assert cache.resolve_reference("turn off that light") == "light.kitchen"


def test_resolve_that_switch():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")

    assert cache.resolve_reference("turn on that switch") == "switch.garage"


def test_resolve_expired_record():
    """Expired records should not be resolved."""
    cache = ActionCache(max_age=1.0)
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache._history[0].timestamp = time.monotonic() - 2.0

    assert cache.resolve_reference("turn off that light") is None


# ---------------------------------------------------------------------------
# format_context
# ---------------------------------------------------------------------------


def test_format_context_single():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    ctx = cache.format_context()
    assert ctx.startswith("Recent actions:")
    assert "turn on" in ctx
    assert "Kitchen Lights" in ctx


def test_format_context_multiple():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen Lights")
    cache.record("switch.garage", "switch", "turn_off", "Garage Switch")
    ctx = cache.format_context()
    assert "Kitchen Lights" in ctx
    assert "Garage Switch" in ctx
    # Newest first
    assert ctx.index("Garage Switch") < ctx.index("Kitchen Lights")


def test_format_context_empty():
    cache = ActionCache()
    assert cache.format_context() == ""


# ---------------------------------------------------------------------------
# conversation_id filtering
# ---------------------------------------------------------------------------


def test_get_recent_filters_by_conversation_id():
    cache = ActionCache()
    cache.record("light.kitchen", "light", "turn_on", "Kitchen", conversation_id="conv1")
    cache.record("switch.garage", "switch", "turn_off", "Garage", conversation_id="conv2")

    recent = cache.get_recent(conversation_id="conv1")
    assert len(recent) == 1
    assert recent[0].entity_id == "light.kitchen"
