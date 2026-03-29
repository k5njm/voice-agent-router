"""Compiled regex patterns for matching voice commands to intent categories."""

from __future__ import annotations

import re

# Each entry: (pattern_name, compiled_regex, handler_name)
# Patterns are tried in order; first match wins.
INTENT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # --- ON / OFF -----------------------------------------------------------
    (
        "ON_OFF_PREFIX",
        re.compile(
            r"(turn|switch)\s+(on|off)\s+(the\s+)?(?P<entity>.+)",
            re.IGNORECASE,
        ),
        "handle_on_off",
    ),
    (
        "ON_OFF_SUFFIX",
        re.compile(
            r"(?P<entity>.+)\s+(on|off)",
            re.IGNORECASE,
        ),
        "handle_on_off",
    ),
    # --- BRIGHTNESS ---------------------------------------------------------
    (
        "BRIGHTNESS",
        re.compile(
            r"(set|dim|brighten)\s+(the\s+)?(?P<entity>.+?)\s+to\s+"
            r"(?P<value>\d+)(\s+percent)?",
            re.IGNORECASE,
        ),
        "handle_brightness",
    ),
    # --- TEMPERATURE --------------------------------------------------------
    (
        "TEMPERATURE",
        re.compile(
            r"set\s+(the\s+)?(thermostat|temperature|temp)\s+to\s+"
            r"(?P<value>\d+)(\s+degrees)?",
            re.IGNORECASE,
        ),
        "handle_temperature",
    ),
    # --- LOCK / UNLOCK ------------------------------------------------------
    (
        "LOCK",
        re.compile(
            r"(?P<action>lock|unlock)\s+(the\s+)?(?P<entity>.+)",
            re.IGNORECASE,
        ),
        "handle_lock",
    ),
    # --- COVER (open / close) -----------------------------------------------
    (
        "COVER",
        re.compile(
            r"(?P<action>open|close)\s+(the\s+)?(?P<entity>.+)",
            re.IGNORECASE,
        ),
        "handle_cover",
    ),
    # --- SCENE --------------------------------------------------------------
    (
        "SCENE",
        re.compile(
            r"(activate|set|run)\s+(the\s+)?(?P<scene>.+?)\s+scene",
            re.IGNORECASE,
        ),
        "handle_scene",
    ),
    # --- STATE QUERY --------------------------------------------------------
    (
        "STATE_QUERY",
        re.compile(
            r"(what\s+is|what's|is)\s+(the\s+)?"
            r"(?P<entity>.+?)"
            r"(\s+(on|off|open|closed|temperature|state|status))?\??",
            re.IGNORECASE,
        ),
        "handle_state_query",
    ),
]
