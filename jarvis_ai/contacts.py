"""Local contact storage for confirmation-first messaging features."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Contact:
    """A validated local contact."""

    name: str
    phone: str
    aliases: tuple[str, ...]

    @property
    def display_name(self) -> str:
        return self.name.title()


class ContactStore:
    """Read contacts from a local JSON file without exposing them to Gemini."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _normalise_name(value: str) -> str:
        return " ".join(value.lower().strip().split())

    @staticmethod
    def _normalise_phone(value: object) -> str | None:
        digits = re.sub(r"\D", "", str(value))
        if not 8 <= len(digits) <= 15:
            return None
        return digits

    def _load(self) -> dict[str, Contact]:
        if not self.path.exists():
            return {}

        try:
            raw_contacts = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(raw_contacts, dict):
            return {}

        contacts: dict[str, Contact] = {}
        for raw_name, raw_details in raw_contacts.items():
            name = self._normalise_name(str(raw_name))
            if not name or not isinstance(raw_details, dict):
                continue

            phone = self._normalise_phone(raw_details.get("phone", ""))
            if not phone:
                continue

            aliases: list[str] = []
            raw_aliases = raw_details.get("aliases", [])
            if isinstance(raw_aliases, list):
                for raw_alias in raw_aliases:
                    alias = self._normalise_name(str(raw_alias))
                    if alias and alias not in aliases:
                        aliases.append(alias)

            contacts[name] = Contact(
                name=name,
                phone=phone,
                aliases=tuple(aliases),
            )
        return contacts

    def aliases(self) -> dict[str, str]:
        """Map every spoken name and alias to its canonical contact name."""

        result: dict[str, str] = {}
        for name, contact in self._load().items():
            result[name] = name
            for alias in contact.aliases:
                result.setdefault(alias, name)
        return result

    def resolve(self, requested_name: str) -> Contact | None:
        normalised = self._normalise_name(requested_name)
        contacts = self._load()
        canonical_name = self.aliases().get(normalised)
        return contacts.get(canonical_name) if canonical_name else None
