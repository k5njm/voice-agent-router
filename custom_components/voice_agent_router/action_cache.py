"""LRU action cache for conversation context — remembers recent actions for pronoun resolution."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass

# Patterns that indicate a reference to a previously-acted-upon entity.
# Each tuple: (compiled regex, optional domain hint extracted from the reference)
_REFERENCE_PATTERNS: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r"\bthat\s+light\b", re.IGNORECASE), "light"),
    (re.compile(r"\bthat\s+switch\b", re.IGNORECASE), "switch"),
    (re.compile(r"\bthat\s+fan\b", re.IGNORECASE), "fan"),
    (re.compile(r"\bthat\s+lock\b", re.IGNORECASE), "lock"),
    (re.compile(r"\bthat\s+cover\b", re.IGNORECASE), "cover"),
    (re.compile(r"\bthe\s+same\s+light\b", re.IGNORECASE), "light"),
    (re.compile(r"\bthe\s+same\s+switch\b", re.IGNORECASE), "switch"),
    (re.compile(r"\bthe\s+same\s+one\b", re.IGNORECASE), None),
    (re.compile(r"\bthat\s+one\b", re.IGNORECASE), None),
    (re.compile(r"\bit\b", re.IGNORECASE), None),
]


@dataclass
class ActionRecord:
    """A single recorded action."""

    entity_id: str
    domain: str
    service: str
    friendly_name: str
    timestamp: float
    conversation_id: str | None = None


class ActionCache:
    """Bounded LRU cache of recently-executed actions.

    Used to resolve anaphoric references like "that light" or "it" back to the
    entity that was most recently acted upon.
    """

    def __init__(self, max_size: int = 10, max_age: float = 300.0) -> None:
        self._history: deque[ActionRecord] = deque(maxlen=max_size)
        self._max_age = max_age

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        entity_id: str,
        domain: str,
        service: str,
        friendly_name: str,
        conversation_id: str | None = None,
    ) -> None:
        """Append an action to the history."""
        self._history.append(
            ActionRecord(
                entity_id=entity_id,
                domain=domain,
                service=service,
                friendly_name=friendly_name,
                timestamp=time.monotonic(),
                conversation_id=conversation_id,
            )
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_recent(
        self,
        max_age: float | None = None,
        conversation_id: str | None = None,
    ) -> list[ActionRecord]:
        """Return entries within *max_age* seconds, newest first.

        If *conversation_id* is given, only entries for that conversation are
        returned.
        """
        cutoff = time.monotonic() - (max_age if max_age is not None else self._max_age)
        results: list[ActionRecord] = []
        for record in reversed(self._history):
            if record.timestamp < cutoff:
                continue
            if conversation_id is not None and record.conversation_id != conversation_id:
                continue
            results.append(record)
        return results

    def get_last_entity(self, domain: str | None = None) -> ActionRecord | None:
        """Return the most recent record within *max_age*, optionally filtered by domain."""
        cutoff = time.monotonic() - self._max_age
        for record in reversed(self._history):
            if record.timestamp < cutoff:
                return None
            if domain is not None and record.domain != domain:
                continue
            return record
        return None

    # ------------------------------------------------------------------
    # Pronoun / reference resolution
    # ------------------------------------------------------------------

    def resolve_reference(self, text: str) -> str | None:
        """Detect anaphoric references in *text* and return the matching entity_id.

        Returns ``None`` if no reference pattern is found or the cache has no
        suitable recent entry.
        """
        for pattern, domain_hint in _REFERENCE_PATTERNS:
            if pattern.search(text):
                record = self.get_last_entity(domain=domain_hint)
                if record is not None:
                    return record.entity_id
        return None

    # ------------------------------------------------------------------
    # LLM context formatting
    # ------------------------------------------------------------------

    def format_context(self) -> str:
        """Format recent actions as a compact string suitable for an LLM system prompt."""
        recent = self.get_recent()
        if not recent:
            return ""

        now = time.monotonic()
        parts: list[str] = []
        for rec in recent:
            ago = int(now - rec.timestamp)
            service_label = rec.service.replace("_", " ")
            parts.append(f"{service_label} {rec.friendly_name} ({ago}s ago)")

        return "Recent actions: " + ", ".join(parts) + "."
