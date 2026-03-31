"""Tests for entity context pre-fetching."""

from __future__ import annotations


class TestGetPrioritySnapshot:
    """Tests for EntityCache.get_priority_snapshot()."""

    def test_light_with_brightness(self, entity_cache):
        """Light entity includes brightness in snapshot."""
        result = entity_cache.get_priority_snapshot(["light.living_room"])
        assert "Living Room Light=on" in result
        assert "brightness:200" in result
        assert result.startswith("Current entity states: ")

    def test_light_without_brightness(self, entity_cache):
        """Light entity without brightness omits the extra."""
        result = entity_cache.get_priority_snapshot(["light.kitchen_lights"])
        assert "Kitchen Lights=off" in result
        assert "brightness" not in result

    def test_climate_with_temperature(self, entity_cache):
        """Climate entity includes temperature in snapshot."""
        result = entity_cache.get_priority_snapshot(["climate.downstairs"])
        assert "Downstairs Thermostat=heat" in result
        assert "temp:72" in result

    def test_basic_entity(self, entity_cache):
        """Non-domain-specific entity shows name=state only."""
        result = entity_cache.get_priority_snapshot(["lock.front_door"])
        assert "Front Door Lock=locked" in result
        assert "(" not in result

    def test_multiple_entities(self, entity_cache):
        """Multiple entities are comma-separated."""
        result = entity_cache.get_priority_snapshot(["light.living_room", "climate.downstairs"])
        assert "Living Room Light=on" in result
        assert "Downstairs Thermostat=heat" in result
        assert ", " in result

    def test_missing_entity_skipped(self, entity_cache):
        """Non-existent entity IDs are silently skipped."""
        result = entity_cache.get_priority_snapshot(["light.nonexistent", "light.living_room"])
        assert "Living Room Light=on" in result
        assert "nonexistent" not in result

    def test_all_missing_returns_empty(self, entity_cache):
        """All missing entities returns empty string."""
        result = entity_cache.get_priority_snapshot(["light.nonexistent", "sensor.fake"])
        assert result == ""

    def test_empty_list_returns_empty(self, entity_cache):
        """Empty entity list returns empty string."""
        result = entity_cache.get_priority_snapshot([])
        assert result == ""

    def test_whitespace_trimmed(self, entity_cache):
        """Whitespace around entity IDs is trimmed."""
        result = entity_cache.get_priority_snapshot(["  light.living_room  ", "  ", ""])
        assert "Living Room Light=on" in result

    def test_cover_entity(self, entity_cache):
        """Cover entity includes position when available."""
        # The mock cover doesn't have current_position, so no extras
        result = entity_cache.get_priority_snapshot(["cover.bedroom_blinds"])
        assert "Bedroom Blinds=open" in result
