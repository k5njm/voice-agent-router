"""Conversation entity for Voice Agent Router."""

from __future__ import annotations

import json
import logging
import time

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
    CONF_SYSTEM_PROMPT_PRESET,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
    PRESET_CUSTOM,
    PRESET_DEFAULT,
    SYSTEM_PROMPT_PRESETS,
)
from .entity_cache import EntityCache
from .perf_log import PerfLogger
from .router import IntentRouter
from .skills.executor import SkillExecutor
from .skills.loader import SkillLoader

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

    skill_loader = hass.data[DOMAIN][config_entry.entry_id].get("skill_loader")

    async_add_entities([VoiceAgentRouterConversationEntity(config_entry, cache, skill_loader)])


class VoiceAgentRouterConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
):
    """Voice Agent Router conversation entity with local fast-path routing."""

    _attr_has_entity_name = True
    _attr_name = "Voice Agent Router"

    def __init__(
        self,
        config_entry: ConfigEntry,
        entity_cache: EntityCache,
        skill_loader: SkillLoader | None = None,
    ) -> None:
        self._config_entry = config_entry
        self._entity_cache = entity_cache
        self._intent_router = IntentRouter(entity_cache)
        self._skill_loader = skill_loader
        self._skill_executor: SkillExecutor | None = None
        self._attr_unique_id = f"{config_entry.entry_id}_conversation"
        self._perf_log: PerfLogger | None = None

    @property
    def supported_languages(self) -> list[str] | str:
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """Register as a conversation agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self._config_entry, self)
        self._perf_log = PerfLogger(self.hass.config.config_dir)
        self._skill_executor = SkillExecutor(self.hass, self._entity_cache)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the conversation agent and tear down cache."""
        conversation.async_unset_agent(self.hass, self._config_entry)
        await self._entity_cache.async_teardown()
        if self._perf_log:
            self._perf_log.close()
        await super().async_will_remove_from_hass()

    def _get_system_prompt(self) -> str:
        """Return the active system prompt, resolving presets."""
        preset = self._get_config(CONF_SYSTEM_PROMPT_PRESET, PRESET_DEFAULT)
        if preset == PRESET_CUSTOM:
            return self._get_config(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)
        return SYSTEM_PROMPT_PRESETS.get(preset, SYSTEM_PROMPT_PRESETS[PRESET_DEFAULT])

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: ChatLog,
    ) -> conversation.ConversationResult:
        """Handle an incoming voice/text message."""
        text = user_input.text
        t_start = time.monotonic()

        # Try local fast-path routing
        enable_local = self._config_entry.options.get(CONF_ENABLE_LOCAL_ROUTER, True)
        if enable_local:
            try:
                action = await self._intent_router.route(text)
                if action is not None:
                    result = await self._execute_local(user_input, action, chat_log)
                    self._write_perf_log(
                        text=text,
                        route="local",
                        pattern=action.service,
                        entity_id=action.entity_id,
                        response=action.speech,
                        latency_ms=round((time.monotonic() - t_start) * 1000),
                    )
                    return result
            except Exception:
                _LOGGER.exception("Local intent router failed for text: '%s'", text)
                # Fall through to cloud LLM

        # Try skill matching before LLM fallback
        skill_context: dict | None = None
        if self._skill_loader is not None:
            try:
                skill_match = self._skill_loader.match_with_score(text)
                if skill_match is not None:
                    skill, score = skill_match
                    if not skill.requires_llm and self._skill_executor is not None:
                        # Template skill — execute directly
                        _LOGGER.debug(
                            "Skill match '%s' (score=%.2f) for '%s'",
                            skill.name,
                            score,
                            text,
                        )
                        response_text = await self._skill_executor.execute_template_skill(skill)
                        self._write_perf_log(
                            text=text,
                            route="skill",
                            skill_name=skill.name,
                            skill_score=score,
                            response=response_text,
                            latency_ms=round((time.monotonic() - t_start) * 1000),
                        )
                        return _speech_result(user_input, response_text)
                    elif skill.requires_llm:
                        # LLM-backed skill — inject context into LLM path
                        _LOGGER.debug(
                            "LLM skill match '%s' (score=%.2f) for '%s'",
                            skill.name,
                            score,
                            text,
                        )
                        skill_context = (
                            self._skill_executor.get_llm_skill_context(skill)
                            if self._skill_executor
                            else None
                        )
            except Exception:
                _LOGGER.exception("Skill matching failed for text: '%s'", text)

        # Cloud LLM fallback via OpenRouter
        _LOGGER.debug("No local match for '%s', falling back to cloud LLM", text)

        # Log near-miss skill matches for diagnostics
        if self._skill_loader is not None:
            try:
                near_miss = self._skill_loader.nearest_miss(text)
                if near_miss is not None:
                    _LOGGER.info(
                        "Skill near-miss for '%s': skill='%s' score=%.2f",
                        text,
                        near_miss[0],
                        near_miss[1],
                    )
                    self._write_perf_log(
                        text=text,
                        route="llm",
                        skill_near_miss=near_miss[0],
                        skill_near_miss_score=near_miss[1],
                    )
            except Exception:
                _LOGGER.debug("Near-miss check failed", exc_info=True)

        # Determine system prompt — use skill context if available
        system_prompt = (
            skill_context["system_prompt"]
            if skill_context and skill_context.get("system_prompt")
            else self._get_system_prompt()
        )

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                "assist",
                system_prompt,
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

        llm_trace: list[dict] = []
        try:
            llm_trace = await self._async_handle_chat_log(chat_log)
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

        result = conversation.async_get_result_from_chat_log(user_input, chat_log)
        response_text = result.response.speech.get("plain", {}).get("speech", "")
        self._write_perf_log(
            text=text,
            route="llm",
            response=response_text,
            iterations=len(llm_trace),
            llm_trace=llm_trace,
            latency_ms=round((time.monotonic() - t_start) * 1000),
        )
        return result

    def _write_perf_log(self, **kwargs) -> None:
        if self._perf_log:
            self._perf_log.log(kwargs)

    def _get_config(self, key: str, default):
        """Read a config value from options first, then data, then default."""
        return self._config_entry.options.get(key, self._config_entry.data.get(key, default))

    async def _async_handle_chat_log(self, chat_log: ChatLog) -> list[dict]:
        """Run the OpenRouter tool-calling loop. Returns per-iteration trace records."""
        trace: list[dict] = []
        client = await self.hass.async_add_executor_job(
            lambda: openai.AsyncOpenAI(
                api_key=self._config_entry.data[CONF_API_KEY],
                base_url="https://openrouter.ai/api/v1",
                timeout=30.0,
            )
        )

        model = self._get_config(CONF_MODEL, DEFAULT_MODEL)
        temperature = self._get_config(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)
        max_iterations = self._get_config(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS)

        # Convert chat_log.content to OpenAI message format
        messages = _convert_chat_log_to_messages(chat_log)

        # Convert HA tools to OpenAI function-calling format
        tools = _convert_tools(chat_log.llm_api.tools) if chat_log.llm_api else []

        for _iteration in range(max_iterations):
            iter_start = time.monotonic()
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

            iter_ms = round((time.monotonic() - iter_start) * 1000)

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
            tool_calls_trace = []
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
                    tool_calls_trace.append({"tool": tc.function.name, "args": tool_args})

            assistant_content = conversation.AssistantContent(
                agent_id=self.entity_id,
                content=message.content or "",
                tool_calls=tool_calls_list,
            )

            # Add to chat log -- this auto-executes HA tool calls
            new_content: list = []
            tool_results_trace = []
            async for tool_result in chat_log.async_add_assistant_content(assistant_content):
                new_content.append(tool_result)
                tool_results_trace.append(
                    {"tool": tool_result.tool_call_id, "result": tool_result.tool_result}
                )

            trace.append(
                {
                    "iteration": _iteration + 1,
                    "latency_ms": iter_ms,
                    "tool_calls": tool_calls_trace,
                    "tool_results": tool_results_trace,
                    "finish_reason": choice.finish_reason,
                }
            )

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

        return trace

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
