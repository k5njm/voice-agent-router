"""Conversation entity for Voice Agent Router."""

from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.components.conversation import ChatLog
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_LOCAL_ROUTER, DOMAIN
from .entity_cache import EntityCache
from .router import IntentRouter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the conversation entity."""
    cache = EntityCache(hass)
    await cache.async_setup()
    hass.data[DOMAIN][config_entry.entry_id]["entity_cache"] = cache

    async_add_entities(
        [VoiceAgentRouterConversationEntity(config_entry, cache)]
    )


class VoiceAgentRouterConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
):
    """Voice Agent Router conversation entity with local fast-path routing."""

    _attr_has_entity_name = True
    _attr_name = "Voice Agent Router"

    def __init__(self, config_entry: ConfigEntry, entity_cache: EntityCache) -> None:
        self._config_entry = config_entry
        self._entity_cache = entity_cache
        self._intent_router = IntentRouter(entity_cache)
        self._attr_unique_id = f"{config_entry.entry_id}_conversation"

    @property
    def supported_languages(self) -> list[str] | str:
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """Register as a conversation agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self._config_entry, self)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the conversation agent and tear down cache."""
        conversation.async_unset_agent(self.hass, self._config_entry)
        await self._entity_cache.async_teardown()
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: ChatLog,
    ) -> conversation.ConversationResult:
        """Handle an incoming voice/text message."""
        text = user_input.text

        # Try local fast-path routing
        enable_local = self._config_entry.options.get(CONF_ENABLE_LOCAL_ROUTER, True)
        if enable_local:
            action = await self._intent_router.route(text)
            if action is not None:
                return await self._execute_local(user_input, action, chat_log)

        # No local match — Phase 2 will add LLM fallback here
        _LOGGER.debug("No local match for: %s", text)
        return _error_result(
            user_input,
            "I can't help with that yet. Local-only mode is active.",
        )

    async def _execute_local(
        self,
        user_input: conversation.ConversationInput,
        action,
        chat_log: ChatLog,
    ) -> conversation.ConversationResult:
        """Execute a locally-routed action via HA service call."""
        if action.service == "query":
            # State query — no service call needed
            return _speech_result(user_input, action.speech)

        try:
            await self.hass.services.async_call(
                action.domain,
                action.service,
                {**action.service_data, "entity_id": action.entity_id},
                blocking=True,
                context=user_input.context,
            )
        except Exception:
            _LOGGER.exception("Failed to execute local action: %s", action)
            return _error_result(
                user_input,
                f"Sorry, I couldn't {action.service.replace('_', ' ')} that.",
            )

        return _speech_result(user_input, action.speech)


def _speech_result(
    user_input: conversation.ConversationInput,
    speech: str,
) -> conversation.ConversationResult:
    """Build a ConversationResult with a speech response."""
    from homeassistant.helpers import intent as intent_helper

    response = intent_helper.IntentResponse(language=user_input.language)
    response.async_set_speech(speech)
    return conversation.ConversationResult(
        response=response,
        conversation_id=user_input.conversation_id,
    )


def _error_result(
    user_input: conversation.ConversationInput,
    speech: str,
) -> conversation.ConversationResult:
    """Build a ConversationResult for an error/unmatched case."""
    from homeassistant.helpers import intent as intent_helper

    response = intent_helper.IntentResponse(language=user_input.language)
    response.async_set_error(
        intent_helper.IntentResponseErrorCode.NO_INTENT_MATCH,
        speech,
    )
    return conversation.ConversationResult(
        response=response,
        conversation_id=user_input.conversation_id,
    )
