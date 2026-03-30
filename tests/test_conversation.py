"""Tests for the conversation entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_speech_result():
    """Test the _speech_result helper."""
    from custom_components.voice_agent_router.conversation import _speech_result

    user_input = MagicMock()
    user_input.language = "en"
    user_input.conversation_id = "test-123"

    result = _speech_result(user_input, "Hello world")
    assert result.conversation_id == "test-123"
    assert result.response.speech["plain"]["speech"] == "Hello world"


@pytest.mark.asyncio
async def test_error_result():
    """Test the _error_result helper."""
    from custom_components.voice_agent_router.conversation import _error_result

    user_input = MagicMock()
    user_input.language = "en"
    user_input.conversation_id = "test-456"

    result = _error_result(user_input, "Something went wrong")
    assert result.conversation_id == "test-456"
