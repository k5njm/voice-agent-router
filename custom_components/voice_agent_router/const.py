"""Constants for Voice Agent Router."""

DOMAIN = "voice_agent_router"

CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_SYSTEM_PROMPT = "system_prompt"
CONF_TEMPERATURE = "temperature"
CONF_MAX_TOOL_ITERATIONS = "max_tool_iterations"
CONF_ENABLE_LOCAL_ROUTER = "enable_local_router"
CONF_LLM_HASS_API = "llm_hass_api"
CONF_SEND_BUG_REPORTS = "send_bug_reports"

# Sentry DSN — reports go to the project maintainer's Sentry instance.
# Replace with the real DSN from https://nick-mccarthy.sentry.io/settings/projects/voice-agent-router/keys/
SENTRY_DSN = ""

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOOL_ITERATIONS = 10
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful voice assistant for a smart home. "
    "Be concise — your responses will be spoken aloud. "
    "Use the available tools to control devices and answer questions about the home."
)
