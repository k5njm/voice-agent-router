# Voice Agent Router

[![CI](https://github.com/k5njm/voice-agent-router/actions/workflows/ci.yml/badge.svg)](https://github.com/k5njm/voice-agent-router/actions/workflows/ci.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A Home Assistant custom integration that provides an intelligent voice assistant with local fast-path routing for common commands (works offline) and cloud LLM fallback via OpenRouter for complex queries. Supports MCP server integration and a YAML-based skill system.

## Features

- **Local intent routing** -- regex-based matching handles lights, switches, locks, covers, climate, scenes, and state queries with zero latency and no cloud dependency.
- **Cloud LLM fallback** -- unmatched commands are forwarded to OpenRouter (OpenAI-compatible) with full Home Assistant tool-calling support.
- **MCP server integration** -- connect external Model Context Protocol servers to extend the assistant's tool set.
- **YAML skill system** -- define custom skills in simple YAML files with trigger patterns, response templates, and optional LLM backing.
- **Entity cache with fuzzy matching** -- spoken names are resolved to entity IDs using token-overlap scoring, so users do not need to memorize exact names.
- **Configurable via UI** -- set up API keys, model selection, system prompts, and feature toggles through the Home Assistant config flow.

## Architecture

```
Voice Input
    |
    v
+-----------------------+
| Conversation Entity   |
+-----------------------+
    |
    v
+-----------------------+     match     +------------------+
| Intent Router         | -----------> | Local Execution  |
| (regex fast-path)     |              | (HA service call)|
+-----------------------+              +------------------+
    | no match
    v
+-----------------------+     match     +------------------+
| Skill Loader          | -----------> | Skill Executor   |
| (YAML patterns)       |              | (template / LLM) |
+-----------------------+              +------------------+
    | no match
    v
+-----------------------+              +------------------+
| OpenRouter LLM        | <---------> | HA LLM Tools     |
| (tool-calling loop)   |             | + MCP Tools      |
+-----------------------+              +------------------+
```

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations** and click the three-dot menu.
3. Select **Custom repositories** and add the repository URL with category **Integration**.
4. Search for "Voice Agent Router" and install it.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/voice_agent_router` directory into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **Voice Agent Router**.
3. Enter your OpenRouter API key.
4. Configure options:
   - **Model** -- the OpenRouter model ID (default: `google/gemini-2.5-flash-preview`).
   - **System prompt** -- instructions sent to the LLM on every request.
   - **Temperature** -- controls LLM response randomness (0.0 -- 1.0).
   - **Enable local router** -- toggle the regex fast-path on or off.
   - **Max tool iterations** -- limit on LLM tool-calling rounds.
5. Select the conversation agent under **Settings > Voice Assistants**.

## Skills

Skills are YAML files placed in the `skills/` directory at the repository root (or a configured path). Each file defines a trigger pattern, an optional LLM backing, and a response template.

### Example skill

```yaml
name: weather_report
description: "Get a weather summary"
trigger:
  patterns:
    - "what's the weather"
    - "weather report"
    - "how's the weather"
requires_llm: true
system_prompt: "Summarize the current weather using the provided sensor data."
tools:
  - ha_get_state
entities:
  - sensor.outdoor_temp
  - sensor.outdoor_humidity
```

Skills with `requires_llm: false` return the `response_template` directly. Skills with `requires_llm: true` invoke the cloud LLM with the specified system prompt and tools.

## Development

### Setup

```bash
git clone https://github.com/k5njm/voice-agent-router.git
cd voice-agent-router

# Create a venv and install test dependencies
python3.12 -m venv .venv
.venv/bin/pip install pytest pytest-asyncio pyyaml

# Install pre-commit hooks (runs ruff + pytest before every commit)
pip install pre-commit
pre-commit install
```

### Running tests

```bash
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

Tests use lightweight stubs for Home Assistant modules (`tests/ha_stubs.py`) so no HA installation is required.

### Linting

```bash
# Check and auto-fix
ruff check --fix custom_components/
ruff format custom_components/

# Or via pre-commit (runs on all files)
pre-commit run --all-files
```

Pre-commit runs automatically on `git commit`: trailing whitespace, YAML/JSON validation, ruff lint+format, and the full test suite. A failing test blocks the commit.

## CI/CD

### CI (`ci.yml`)

Runs on every push and pull request to `main`:

| Job | What it does |
|-----|-------------|
| `lint` | `ruff check` + `ruff format --check` on `custom_components/` |
| `test` | `pytest tests/ -v` on Python 3.12 with `PYTHONPATH` set |

### Releases (`release.yml`)

Push a version tag to create a GitHub Release with auto-generated notes:

```bash
git tag v0.2.0
git push origin v0.2.0
```

GitHub Actions picks up the tag, runs `softprops/action-gh-release`, and publishes the release. HACS users will see the new version automatically.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
