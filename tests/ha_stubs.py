"""Stub out Home Assistant modules for unit tests.

Inserted into sys.modules before test collection so our custom_component
code can be imported without a full HA installation.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Core HA stubs
# ---------------------------------------------------------------------------

_ha_core = MagicMock()
_ha_core.HomeAssistant = object
_ha_core.State = object
_ha_core.callback = lambda f: f  # passthrough decorator

_ha_config_entries = MagicMock()
_ha_config_entries.ConfigEntry = object
_ha_config_entries.ConfigFlow = object
_ha_config_entries.OptionsFlow = object

_ha_const = MagicMock()
_ha_const.Platform = MagicMock()
_ha_const.Platform.CONVERSATION = "conversation"
_ha_const.MATCH_ALL = "*"

_ha_data_entry_flow = MagicMock()
_ha_data_entry_flow.FlowResult = object

_ha_helpers_event = MagicMock()
_ha_helpers_intent = MagicMock()
_ha_helpers_template = MagicMock()


# IntentResponse needs to be a real class so we can subclass/call it
class _FakeIntentResponse:
    def __init__(self, language=None):
        self.language = language
        self.speech = {}
        self._error_code = None
        self._error_message = None

    def async_set_speech(self, speech):
        self.speech = {"plain": {"speech": speech}}

    def async_set_error(self, code, message):
        self._error_code = code
        self._error_message = message


_ha_helpers_intent.IntentResponse = _FakeIntentResponse
_ha_helpers_intent.IntentResponseErrorCode = MagicMock()

_ha_helpers_llm = MagicMock()
_ha_helpers_llm.Tool = object
_ha_helpers_llm.API = object


class _FakeAPIInstance:
    def __init__(self, api, api_prompt, llm_context, tools, custom_serializer=None):
        self.api = api
        self.api_prompt = api_prompt
        self.llm_context = llm_context
        self.tools = tools
        self.custom_serializer = custom_serializer


_ha_helpers_llm.APIInstance = _FakeAPIInstance
_ha_helpers_llm.ToolInput = MagicMock()
_ha_helpers_llm.LLMContext = MagicMock()

# conversation component stubs
_ha_conv = MagicMock()
_ha_conv.ConversationEntity = object
_ha_conv.AbstractConversationAgent = object
_ha_conv.ConversationEntityFeature = MagicMock()


class _FakeConversationResult:
    def __init__(self, response, conversation_id=None, continue_conversation=False):
        self.response = response
        self.conversation_id = conversation_id
        self.continue_conversation = continue_conversation


_ha_conv.ConversationResult = _FakeConversationResult
_ha_conv.ConversationInput = MagicMock()
_ha_conv.AssistantContent = MagicMock()
_ha_conv.ConverseError = Exception
_ha_conv.async_set_agent = MagicMock()
_ha_conv.async_unset_agent = MagicMock()
_ha_conv.async_get_result_from_chat_log = MagicMock()
_ha_conv.ChatLog = MagicMock()

_ha_entity_platform = MagicMock()
_ha_entity_platform.AddEntitiesCallback = object

_ha_json = MagicMock()
_ha_json.JsonObjectType = dict

# ---------------------------------------------------------------------------
# Register all stubs in sys.modules
# ---------------------------------------------------------------------------

STUBS = {
    "homeassistant": MagicMock(),
    "homeassistant.core": _ha_core,
    "homeassistant.config_entries": _ha_config_entries,
    "homeassistant.const": _ha_const,
    "homeassistant.data_entry_flow": _ha_data_entry_flow,
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.event": _ha_helpers_event,
    "homeassistant.helpers.intent": _ha_helpers_intent,
    "homeassistant.helpers.llm": _ha_helpers_llm,
    "homeassistant.helpers.template": _ha_helpers_template,
    "homeassistant.helpers.entity_platform": _ha_entity_platform,
    "homeassistant.components": MagicMock(),
    "homeassistant.components.conversation": _ha_conv,
    "homeassistant.util": MagicMock(),
    "homeassistant.util.json": _ha_json,
    "voluptuous": MagicMock(),
    "voluptuous_openapi": MagicMock(),
    "openai": MagicMock(),
    "mcp": MagicMock(),
    "mcp.client": MagicMock(),
    "mcp.client.stdio": MagicMock(),
}


def install() -> None:
    """Insert all stubs — call before any custom_component imports."""
    for name, stub in STUBS.items():
        if name not in sys.modules:
            sys.modules[name] = stub

    # Wire child stubs as attributes on parents so that
    # `from homeassistant.helpers import llm` resolves correctly
    sys.modules["homeassistant"].helpers = sys.modules["homeassistant.helpers"]
    sys.modules["homeassistant"].components = sys.modules["homeassistant.components"]
    sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]
    sys.modules["homeassistant"].const = sys.modules["homeassistant.const"]
    sys.modules["homeassistant"].core = sys.modules["homeassistant.core"]
    sys.modules["homeassistant.helpers"].llm = sys.modules["homeassistant.helpers.llm"]
    sys.modules["homeassistant.helpers"].event = sys.modules["homeassistant.helpers.event"]
    sys.modules["homeassistant.helpers"].intent = sys.modules["homeassistant.helpers.intent"]
    sys.modules["homeassistant.helpers"].template = sys.modules["homeassistant.helpers.template"]
    sys.modules["homeassistant.helpers"].entity_platform = sys.modules[
        "homeassistant.helpers.entity_platform"
    ]
    sys.modules["homeassistant.components"].conversation = sys.modules[
        "homeassistant.components.conversation"
    ]
