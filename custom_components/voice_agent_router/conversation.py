"""Conversation entity for Voice Agent Router."""

from __future__ import annotations

import json
import logging

import openai
import voluptuous_openapi
from homeassistant.components import conversation
from homeassistant.components.conversation import ChatLog
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_API_KEY,
    CONF_ENABLE_LOCAL_ROUTER,
    CONF_MAX_TOOL_ITERATIONS,
    CONF_MODEL,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
)
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
    try:
        await cache.async_setup()
    except Exception:
        _LOGGER.exception("Entity cache setup failed; continuing with empty cache")
    hass.data[DOMAIN][config_entry.entry_id]["entity_cache"] = cache

    async_add_entities([VoiceAgentRouterConversationEntity(config_entry, cache)])


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

    def _get_system_prompt(self) -> str:
        """Return the configured system prompt."""
        return self._config_entry.options.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)

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
            try:
                action = await self._intent_router.route(text)
                if action is not None:
                    return await self._execute_local(user_input, action, chat_log)
            except Exception:
                _LOGGER.exception("Local intent router failed for text: '%s'", text)
                # Fall through to cloud LLM

        # Cloud LLM fallback via OpenRouter
        _LOGGER.debug("No local match for '%s', falling back to cloud LLM", text)

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                "assist",
                self._get_system_prompt(),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()
        except Exception:
            _LOGGER.exception("Failed to provide LLM data for chat log")
            return _error_result(
                user_input,
                "Sorry, I encountered an internal error setting up the assistant.",
            )

        try:
            await self._async_handle_chat_log(chat_log)
        except openai.AuthenticationError as err:
            _LOGGER.error("OpenRouter authentication failed: %s", err)
            return _error_result(
                user_input,
                "Sorry, the cloud LLM authentication failed. Check your API key.",
            )
        except openai.RateLimitError as err:
            _LOGGER.warning("OpenRouter rate limit hit: %s", err)
            return _error_result(
                user_input,
                "Sorry, the cloud assistant is busy right now. Please try again in a moment.",
            )
        except openai.APITimeoutError as err:
            _LOGGER.warning("OpenRouter request timed out: %s", err)
            return _error_result(
                user_input,
                "Sorry, the cloud assistant took too long to respond. Please try again.",
            )
        except openai.APIConnectionError as err:
            _LOGGER.error("OpenRouter connection error: %s", err)
            return _error_result(
                user_input,
                "Sorry, I couldn't connect to the cloud assistant right now.",
            )
        except openai.APIError as err:
            _LOGGER.error("OpenRouter API error: %s", err)
            return _error_result(
                user_input,
                "Sorry, I couldn't reach the cloud assistant right now.",
            )
        except Exception:
            _LOGGER.exception("Unexpected error during cloud LLM conversation")
            return _error_result(
                user_input,
                "Sorry, something went wrong. Please try again.",
            )

        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _async_handle_chat_log(self, chat_log: ChatLog) -> None:
        """Run the OpenRouter tool-calling loop."""
        client = openai.AsyncOpenAI(
            api_key=self._config_entry.data[CONF_API_KEY],
            base_url="https://openrouter.ai/api/v1",
            timeout=30.0,
        )

        model = self._config_entry.options.get(CONF_MODEL, DEFAULT_MODEL)
        temperature = self._config_entry.options.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)
        max_iterations = self._config_entry.options.get(
            CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS
        )

        # Convert chat_log.content to OpenAI message format
        messages = _convert_chat_log_to_messages(chat_log)

        # Convert HA tools to OpenAI function-calling format
        tools = _convert_tools(chat_log.llm_api.tools) if chat_log.llm_api else []

        for _iteration in range(max_iterations):
            _LOGGER.debug(
                "OpenRouter iteration %d/%d, model=%s",
                _iteration + 1,
                max_iterations,
                model,
            )

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools or openai.NOT_GIVEN,
                temperature=temperature,
            )

            if not response.choices:
                _LOGGER.warning(
                    "OpenRouter returned empty choices (model=%s, iteration=%d)",
                    model,
                    _iteration + 1,
                )
                break

            choice = response.choices[0]
            message = choice.message

            # Build tool_calls list if the model requested any
            tool_calls_list = None
            if message.tool_calls:
                tool_calls_list = []
                for tc in message.tool_calls:
                    try:
                        tool_args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError) as err:
                        _LOGGER.warning(
                            "Malformed tool args from LLM (tool=%s, id=%s): %s — skipping",
                            tc.function.name,
                            tc.id,
                            err,
                        )
                        continue
                    tool_calls_list.append(
                        llm.ToolInput(
                            tool_name=tc.function.name,
                            tool_args=tool_args,
                            id=tc.id,
                        )
                    )

            assistant_content = conversation.AssistantContent(
                agent_id=self.entity_id,
                content=message.content or "",
                tool_calls=tool_calls_list,
            )

            # Add to chat log -- this auto-executes HA tool calls
            new_content: list = []
            async for tool_result in chat_log.async_add_assistant_content(assistant_content):
                new_content.append(tool_result)

            if not chat_log.unresponded_tool_results:
                break

            # Append assistant message and tool results for the next iteration
            messages.append(_assistant_to_message(message))
            for result in new_content:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "content": json.dumps(result.tool_result),
                    }
                )

    async def _execute_local(
        self,
        user_input: conversation.ConversationInput,
        action,
        chat_log: ChatLog,
    ) -> conversation.ConversationResult:
        """Execute a locally-routed action via HA service call."""
        if action.service == "query":
            # State query -- no service call needed
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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _convert_chat_log_to_messages(chat_log: ChatLog) -> list[dict]:
    """Convert ChatLog content to OpenAI message format."""
    messages: list[dict] = []
    for content in chat_log.content:
        if content.role == "system":
            messages.append({"role": "system", "content": content.content})
        elif content.role == "user":
            messages.append({"role": "user", "content": content.content})
        elif content.role == "assistant":
            msg: dict = {"role": "assistant", "content": content.content or ""}
            if content.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_args),
                        },
                    }
                    for tc in content.tool_calls
                ]
            messages.append(msg)
        elif content.role == "tool_result":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": content.tool_call_id,
                    "content": json.dumps(content.tool_result),
                }
            )
    return messages


def _assistant_to_message(message) -> dict:
    """Convert an OpenAI ChatCompletionMessage to a dict for re-submission."""
    msg: dict = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return msg


def _convert_tools(tools: list) -> list[dict]:
    """Convert HA LLM tools to OpenAI function-calling format."""
    result: list[dict] = []
    for tool in tools:
        func: dict = {"name": tool.name, "description": tool.description or ""}
        if tool.parameters:
            func["parameters"] = voluptuous_openapi.convert(tool.parameters)
        else:
            func["parameters"] = {"type": "object", "properties": {}}
        result.append({"type": "function", "function": func})
    return result


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
