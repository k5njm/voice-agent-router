"""Tests for follow-up conversation support."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_agent_router.followup import (
    CONVERSATION_END_PHRASES,
    FollowupManager,
    is_conversation_end,
)

# ---------------------------------------------------------------------------
# is_conversation_end tests
# ---------------------------------------------------------------------------


class TestIsConversationEnd:
    """Tests for the is_conversation_end function."""

    @pytest.mark.parametrize(
        "text",
        [
            "thanks",
            "Thank you",
            "that's all",
            "DONE",
            "stop",
            "goodbye",
            "never mind",
            "nope",
            "no thanks",
            "good night",
            "  thanks  ",
            "Thanks!",
            "Thank you.",
            "that is all",
        ],
    )
    def test_end_phrases_detected(self, text: str):
        assert is_conversation_end(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "turn on the kitchen lights",
            "what is the temperature",
            "set the thermostat to 72",
            "play some music",
            "how is the weather",
            "lock the front door",
            "hello",
            "",
        ],
    )
    def test_normal_commands_not_end(self, text: str):
        assert is_conversation_end(text) is False

    def test_embedded_end_phrase(self):
        """End phrases within longer text are also detected."""
        assert is_conversation_end("ok that's all for now") is True
        assert is_conversation_end("ok thank you very much") is True

    def test_all_defined_phrases_are_detected(self):
        """Every phrase in the list should be detected."""
        for phrase in CONVERSATION_END_PHRASES:
            assert is_conversation_end(phrase) is True, f"Failed for: {phrase}"


# ---------------------------------------------------------------------------
# FollowupManager tests
# ---------------------------------------------------------------------------


class TestFollowupManager:
    """Tests for FollowupManager.trigger_relisten."""

    @pytest.fixture
    def manager(self):
        return FollowupManager()

    @pytest.fixture
    def mock_hass(self):
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.mark.asyncio
    async def test_trigger_relisten_with_satellite_id(self, manager, mock_hass):
        """Should call assist_satellite.start_conversation with the satellite entity."""
        with patch(
            "custom_components.voice_agent_router.followup.asyncio.sleep", new_callable=AsyncMock
        ):
            await manager.trigger_relisten(
                mock_hass,
                satellite_id="assist_satellite.living_room",
                device_id=None,
                timeout_seconds=8.0,
            )

        mock_hass.services.async_call.assert_called_once_with(
            "assist_satellite",
            "start_conversation",
            {"entity_id": "assist_satellite.living_room"},
            blocking=True,
        )

    @pytest.mark.asyncio
    async def test_trigger_relisten_no_ids(self, manager, mock_hass):
        """Should not call any service when no satellite_id or device_id."""
        with patch(
            "custom_components.voice_agent_router.followup.asyncio.sleep", new_callable=AsyncMock
        ):
            await manager.trigger_relisten(
                mock_hass,
                satellite_id=None,
                device_id=None,
                timeout_seconds=8.0,
            )

        mock_hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_relisten_service_error(self, manager, mock_hass):
        """Should handle service errors gracefully without raising."""
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("Service not found"))
        with patch(
            "custom_components.voice_agent_router.followup.asyncio.sleep", new_callable=AsyncMock
        ):
            # Should not raise
            await manager.trigger_relisten(
                mock_hass,
                satellite_id="assist_satellite.kitchen",
                device_id=None,
                timeout_seconds=8.0,
            )

    @pytest.mark.asyncio
    async def test_trigger_relisten_with_device_id_fallback(self, manager, mock_hass):
        """Should resolve satellite entity from device_id when satellite_id is None."""
        mock_entry = MagicMock()
        mock_entry.domain = "assist_satellite"
        mock_entry.entity_id = "assist_satellite.bedroom"

        with (
            patch(
                "custom_components.voice_agent_router.followup.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=MagicMock(),
            ),
            patch(
                "homeassistant.helpers.entity_registry.async_entries_for_device",
                return_value=[mock_entry],
            ),
        ):
            await manager.trigger_relisten(
                mock_hass,
                satellite_id=None,
                device_id="device-123",
                timeout_seconds=8.0,
            )

        mock_hass.services.async_call.assert_called_once_with(
            "assist_satellite",
            "start_conversation",
            {"entity_id": "assist_satellite.bedroom"},
            blocking=True,
        )

    @pytest.mark.asyncio
    async def test_trigger_relisten_device_id_no_satellite_entity(self, manager, mock_hass):
        """Should gracefully handle device with no assist_satellite entity."""
        mock_entry = MagicMock()
        mock_entry.domain = "light"
        mock_entry.entity_id = "light.bedroom"

        with (
            patch(
                "custom_components.voice_agent_router.followup.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=MagicMock(),
            ),
            patch(
                "homeassistant.helpers.entity_registry.async_entries_for_device",
                return_value=[mock_entry],
            ),
        ):
            await manager.trigger_relisten(
                mock_hass,
                satellite_id=None,
                device_id="device-456",
                timeout_seconds=8.0,
            )

        # No satellite found, so no service call
        mock_hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: _maybe_schedule_followup on conversation entity
# ---------------------------------------------------------------------------


class TestMaybeScheduleFollowup:
    """Test that _maybe_schedule_followup on the entity works correctly."""

    def _make_entity(self, enable_followup: bool = True, timeout: int = 8):
        """Create a minimal conversation entity with mocked config."""
        from custom_components.voice_agent_router.conversation import (
            VoiceAgentRouterConversationEntity,
        )

        config_entry = MagicMock()
        config_entry.entry_id = "test-entry"
        config_entry.options = {
            "enable_followup": enable_followup,
            "followup_timeout": timeout,
        }
        config_entry.data = {}

        entity_cache = MagicMock()
        entity = VoiceAgentRouterConversationEntity(config_entry, entity_cache)
        entity.hass = MagicMock()
        entity.hass.async_create_task = MagicMock()
        return entity

    def test_followup_disabled(self):
        """No task scheduled when follow-up is disabled."""
        entity = self._make_entity(enable_followup=False)
        user_input = MagicMock()
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.device_id = "dev-1"

        entity._maybe_schedule_followup("turn on the lights", user_input)
        entity.hass.async_create_task.assert_not_called()

    def test_followup_on_end_phrase(self):
        """No task scheduled when user says an end phrase."""
        entity = self._make_entity(enable_followup=True)
        user_input = MagicMock()
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.device_id = "dev-1"

        entity._maybe_schedule_followup("thanks", user_input)
        entity.hass.async_create_task.assert_not_called()

    def test_followup_scheduled(self):
        """Task scheduled for normal command with follow-up enabled."""
        entity = self._make_entity(enable_followup=True)
        user_input = MagicMock()
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.device_id = "dev-1"

        entity._maybe_schedule_followup("turn on the lights", user_input)
        entity.hass.async_create_task.assert_called_once()

    def test_followup_no_satellite_or_device(self):
        """No task scheduled when no satellite_id or device_id."""
        entity = self._make_entity(enable_followup=True)
        user_input = MagicMock()
        user_input.satellite_id = None
        user_input.device_id = None

        entity._maybe_schedule_followup("turn on the lights", user_input)
        entity.hass.async_create_task.assert_not_called()
