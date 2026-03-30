# Voice Agent Router

HA custom integration: voice pipeline conversation agent with local regex fast-path
and cloud LLM fallback via OpenRouter. Distributable via HACS.

## Commands

```bash
# Dev environment (required before tests or pre-commit)
python3.12 -m venv .venv
.venv/bin/pip install pytest pytest-asyncio pyyaml

# Run tests
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Lint + format
ruff check --fix custom_components/
ruff format custom_components/

# Full pre-commit (lint + format + tests)
pre-commit run --all-files

# Deploy to HA for testing
scp -r custom_components/voice_agent_router ha:/homeassistant/custom_components/
ssh ha "ha core restart"

# Release — triggers GitHub Actions release workflow
git tag v0.X.0 && git push origin v0.X.0
```

## Architecture

```
Voice satellite → Parakeet STT → HA Assist Pipeline
                                        ↓
                              VoiceAgentRouterConversationEntity
                                        ↓
                                  IntentRouter (regex fast-path)
                                   /             \
                           match (offline)    no match
                                ↓                  ↓
                          HA service call     SkillLoader (YAML triggers)
                                               /        \
                                         match           no match
                                           ↓                ↓
                                    SkillExecutor      OpenRouter LLM
                                  (template or LLM)   + HA tools + MCP tools
```

## Key Files

```
custom_components/voice_agent_router/
  conversation.py     — ConversationEntity; fast-path check then cloud LLM loop
  entity_cache.py     — fuzzy token-overlap matching of spoken names → entity_ids
  router/             — regex pattern matching → LocalAction dataclass
  skills/             — YAML skill loader + Jinja2/LLM executor
  llm_api/            — MCP and Skill tools registered as HA LLM API
  mcp/client.py       — multi-server MCP stdio client manager

skills/               — example YAML skill definitions (copied to HA config dir)
tests/ha_stubs.py     — sys.modules stubs replacing full HA install for unit tests
```

## Gotchas

- `PYTHONPATH=.` is required for tests — `custom_components/` is not an installable package
- Tests stub out all `homeassistant.*` imports via `tests/ha_stubs.py` (no HA install needed)
- `ha_stubs.install()` must be the first import in `conftest.py` before any `custom_component` import
- `ConversationEntity` and `AbstractConversationAgent` stubs must be distinct classes (not both
  `object`) or Python raises "duplicate base class" on the entity class definition
- `router/__init__.py` must re-export `IntentRouter` — `conversation.py` imports from the package
- `.venv/` is gitignored; contributors must create it manually before pre-commit works
- Pre-commit pytest hook fails if `.venv` doesn't exist — bootstrap the venv first

## Error Reporting (Sentry)

Opt-in via "Send Bug Reports" toggle in integration options. Off by default — zero telemetry
unless the user explicitly enables it. DSN is hardcoded in `const.py` (points to maintainer's
Sentry project). `sentry-sdk` is included in `manifest.json` requirements.

- Sentry org: `nick-mccarthy`
- Sentry project: `voice-agent-router` (platform: python)
- DSN: hardcoded in `const.py` → `SENTRY_DSN` (fill in from Sentry project settings)
- GitHub integration: connect at https://nick-mccarthy.sentry.io/settings/integrations/github/
  to enable suspect commits, stack trace links, and auto issue creation
