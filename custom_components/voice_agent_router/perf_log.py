"""Performance logger — writes one JSONL line per voice interaction."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import Any

_LOGGER = logging.getLogger(__name__)

_LOG_FILENAME = "voice_agent_router_perf.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3


class PerfLogger:
    """Append-only JSONL performance log for voice routing decisions."""

    def __init__(self, config_dir: str) -> None:
        self._path = os.path.join(config_dir, _LOG_FILENAME)
        self._handler = RotatingFileHandler(
            self._path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        self._logger = logging.getLogger(f"{__name__}.file")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._logger.addHandler(self._handler)

    def log(self, record: dict[str, Any]) -> None:
        """Write a single JSONL record."""
        record["ts"] = datetime.now(UTC).isoformat()
        try:
            self._logger.info(json.dumps(record, ensure_ascii=False))
        except Exception:
            _LOGGER.debug("Failed to write perf log entry")

    def close(self) -> None:
        self._handler.close()
        self._logger.removeHandler(self._handler)
