"""Thread-safe JSON storage for simple Jarvis reminders."""

from __future__ import annotations

import json
import threading
from pathlib import Path


class ReminderStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> list[str]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()]

    def _write(self, reminders: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(reminders, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list(self) -> list[str]:
        with self._lock:
            return self._read()

    def add(self, text: str) -> str:
        clean_text = " ".join(text.split()).strip(" .")[:300]
        if not clean_text:
            raise ValueError("Reminder cannot be empty.")
        with self._lock:
            reminders = self._read()
            if clean_text.casefold() not in {
                reminder.casefold() for reminder in reminders
            }:
                reminders.append(clean_text)
                self._write(reminders[-100:])
        return clean_text

    def remove(self, index: int) -> str:
        with self._lock:
            reminders = self._read()
            if index < 0 or index >= len(reminders):
                raise IndexError("Reminder does not exist.")
            removed = reminders.pop(index)
            self._write(reminders)
            return removed

    def spoken_summary(self, *, limit: int = 5) -> str:
        reminders = self.list()
        if not reminders:
            return "You have no saved reminders."
        selected = reminders[:limit]
        summary = " Next reminder: ".join(selected)
        remaining = len(reminders) - len(selected)
        extra = f" You also have {remaining} more." if remaining else ""
        return f"You have {len(reminders)} saved reminders. {summary}.{extra}"
