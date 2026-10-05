"""Small JSON-backed memory store for non-sensitive preferences."""

from __future__ import annotations

import json
import re
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            str(key): str(value)
            for key, value in data.items()
            if isinstance(key, str) and isinstance(value, (str, int, float, bool))
        }

    def save(self, key: str, value: str) -> None:
        safe_key = re.sub(r"[^a-z0-9_]+", "_", key.lower()).strip("_")[:50]
        if not safe_key:
            raise ValueError("Memory key cannot be empty.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        memory = self._read()
        memory[safe_key] = value.strip()[:500]
        self.path.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, key: str) -> str | None:
        safe_key = re.sub(r"[^a-z0-9_]+", "_", key.lower()).strip("_")[:50]
        return self._read().get(safe_key)