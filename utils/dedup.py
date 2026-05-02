"""
Dedup store — tracks which trends have already been launched.
Persists to a JSON file to survive restarts.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("utils.dedup")


class DedupStore:
    def __init__(self, db_path: str = "data/launched.json"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def is_launched(self, key: str) -> bool:
        return key in self._data

    def mark_launched(self, key: str, extra: dict = None):
        self._data[key] = {
            "launched_at": datetime.now(timezone.utc).isoformat(),
            **(extra or {}),
        }
        self._save()
        logger.debug(f"Marked as launched: {key}")

    def get_all(self) -> dict:
        return dict(self._data)

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                return {}
        return {}

    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2))
