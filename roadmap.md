# Voice Agent Router — Roadmap

## 1. Skill Matching Improvements
**Problem:** "Good morning" routes to LLM instead of triggering the good_morning skill.
**Ideas:**
- Audit skill trigger patterns — fuzzy/semantic matching instead of pure regex
- Add a skill confidence threshold; if input is "close enough" to a skill trigger, prefer the skill over LLM fallback
- Log skill miss rate in perf log (route=llm but a skill pattern was close)

## 2. Pre-cached Skill Responses
**Problem:** Skills like good_morning aggregate sensor data and generate a response — slow on demand.
**Ideas:**
- Add optional `cache` block to skill YAML definition:
  ```yaml
  cache:
    cron: "0,15,30,45 6-9 * * *"   # refresh every 15 min, 6-9am
    ttl: 900                         # max age in seconds
  ```
- Background task pre-generates and stores the response; voice request returns cached copy instantly
- Cache invalidated if any listed entity state changes, or on TTL expiry

## 3. Entity Context Pre-fetching
**Problem:** MCP round-trip needed just to discover entity list and states; unnecessary latency.
**Ideas:**
- Define a `priority_entities` list in integration config (commonly voice-controlled devices)
- Entity cache already syncs state every 60s — extend it to push a compact state snapshot into the LLM system prompt context
- For write commands (turn off, dim, lock), skip state lookup — just fire the service call
- Reserve state lookups for query intents only

## 4. Entity Ambiguity Resolution
**Problem:** "Turn off bedroom lamps" acted on overhead light, not the lamp group. Groups and member entities both exist.
**Ideas:**
- When resolving entity names, prefer groups over members if the spoken name matches the group label
- Add domain hints to disambiguation: "lamps" → prefer `light` entities with "lamp" in friendly name
- Allow per-entity aliases in a config file (home-specific, but optional — doesn't affect others)
- Avoid making it an expert system; generalizable heuristics only

## 5. Follow-up Conversations
**Problem:** After a response, user has to re-invoke the wake word for follow-ups; no natural back-and-forth.
**Ideas:**
- After responding, identify the originating voice satellite entity_id from the conversation input
- Call a HA service to kick it back into listening mode (e.g., `assist_satellite.start_conversation` if available)
- Configurable follow-up timeout (e.g., 8 seconds of silence = end conversation)
- User can explicitly end with "that's all" / "thanks" / "stop"
- Needs research: which HA satellite integrations expose a "start listening" service

## 6. Conversation Context (LRU Action Cache)
**Problem:** "Make that light blue" has no reference to which light was just controlled.
**Ideas:**
- Maintain an in-memory LRU cache of recent actions (entity_id, domain, service, timestamp) — last N=10, TTL ~5 min
- When resolving a pronoun/ambiguous reference ("that light", "it", "the same one"), check recent actions first
- Wire into both local router and LLM context: inject most-recently-touched entity into system prompt or pre-message context
- Scope to conversation_id if HA provides one; otherwise time-window based
