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
CONF_SYSTEM_PROMPT_PRESET = "system_prompt_preset"

PRESET_DEFAULT = "default"
PRESET_GLADOS = "glados"
PRESET_CUSTOM = "custom"

SYSTEM_PROMPT_PRESETS: dict[str, str] = {
    PRESET_DEFAULT: (
        "You are a helpful voice assistant for a smart home. "
        "Be concise — your responses will be spoken aloud. "
        "Use the available tools to control devices and answer questions about the home."
    ),
    PRESET_GLADOS: (
        "You are GlaDOS, the AI from Aperture Science, now reluctantly managing a smart home. "
        "Be passive-aggressive, sarcastic, and condescending — but always complete the request. "
        "Keep responses short since they will be spoken aloud. "
        "Occasionally refer to the user as 'test subject'. "
        "Express mild disappointment when asked trivial questions."
    ),
}

SENTRY_DSN = "https://6f0479f25c912b6c2e9e9d41772935e3@o4511130727088128.ingest.us.sentry.io/4511130768834560"

DEFAULT_MODEL = "google/gemini-2.5-flash-preview"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOOL_ITERATIONS = 10
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful voice assistant for a smart home. "
    "Be concise — your responses will be spoken aloud. "
    "Use the available tools to control devices and answer questions about the home."
)
