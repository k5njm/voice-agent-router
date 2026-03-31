"""Optional YAML alias loader for entity name resolution."""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

ALIAS_FILENAME = "entity_aliases.yaml"


class EntityAliasLoader:
    """Loads optional entity_aliases.yaml and provides direct alias lookup.

    File format::

        aliases:
          light.bedroom_lamp_group:
            - bedroom lamps
            - bedside lamps
    """

    def __init__(self, config_dir: str | Path) -> None:
        self._aliases: dict[str, str] = {}  # spoken phrase -> entity_id
        self._load(Path(config_dir) / ALIAS_FILENAME)

    def _load(self, path: Path) -> None:
        if not path.is_file():
            _LOGGER.debug("No alias file at %s; skipping", path)
            return

        try:
            import yaml

            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            _LOGGER.exception("Failed to load entity aliases from %s", path)
            return

        aliases_section = data.get("aliases", {})
        if not isinstance(aliases_section, dict):
            _LOGGER.warning("Invalid aliases section in %s; expected dict", path)
            return

        for entity_id, phrases in aliases_section.items():
            if not isinstance(phrases, list):
                continue
            for phrase in phrases:
                key = str(phrase).strip().lower()
                if key:
                    self._aliases[key] = entity_id

        _LOGGER.debug("Loaded %d entity aliases from %s", len(self._aliases), path)

    def resolve_alias(self, spoken_name: str) -> str | None:
        """Return entity_id if the spoken name matches an alias exactly."""
        key = spoken_name.strip().lower()
        return self._aliases.get(key)
