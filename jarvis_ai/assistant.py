"""High-level orchestration for command routing and execution."""

from __future__ import annotations

from pathlib import Path

import music_library

from .actions import ALLOWED_SITES, SITE_ALIASES, ActionExecutor
from .contacts import Contact, ContactStore
from .memory import MemoryStore
from .models import AssistantResult, CommandDecision
from .reminders import ReminderStore
from .router import GeminiRouter, GeminiRoutingError, RuleRouter


class JarvisAssistant:
    def __init__(self, data_dir: Path, *, dry_run: bool = False) -> None:
        memory = MemoryStore(data_dir / "memory.json")
        reminders = ReminderStore(data_dir / "data" / "reminders.json")
        contacts = ContactStore(data_dir / "contacts.json")
        self.rules = RuleRouter(
            SITE_ALIASES,
            music_library.music,
            contact_aliases=contacts.aliases(),
        )
        self.gemini = GeminiRouter()
        self.executor = ActionExecutor(
            memory,
            reminders=reminders,
            dry_run=dry_run,
            contacts=contacts,
        )
        self._pending_whatsapp: tuple[Contact, str] | None = None

    @property
    def ai_available(self) -> bool:
        return self.gemini.available

    def select_voice_transcript(self, candidates: list[str]) -> str:
        """Prefer a safe, known command if Google includes it as an alternative."""
        primary = candidates[0]
        if self.rules.route(primary) is not None:
            return primary
        safe_alternative_actions = {
            "open_website",
            "get_time",
            "get_date",
            "get_weather",
            "start_my_day",
            "list_reminders",
            "play_favorite_song",
            "prepare_whatsapp_message",
        }
        for candidate in candidates[1:]:
            decision = self.rules.route(candidate)
            if decision is not None and decision.action in safe_alternative_actions:
                return candidate
        return primary

    def list_reminders(self) -> list[str]:
        return self.executor.reminders.list()

    def add_reminder(self, text: str) -> str:
        return self.executor.reminders.add(text)

    def remove_reminder(self, index: int) -> str:
        return self.executor.reminders.remove(index)

    def complete_start_my_day(self) -> str:
        return self.executor.complete_start_my_day()

    def handle(
        self,
        command: str,
        *,
        defer_start_day_actions: bool = False,
    ) -> AssistantResult:
        cleaned = command.strip()
        if not cleaned:
            return AssistantResult(
                message="Please say or type a command.",
                action="unsupported",
                source="fallback",
            )

        normalised = " ".join(cleaned.lower().split()).strip(" .!?")
        if self._pending_whatsapp is not None:
            if normalised in {
                "yes",
                "yes please",
                "confirm",
                "continue",
                "go ahead",
                "open it",
                "do it",
                "haan",
                "ha",
            }:
                contact, message = self._pending_whatsapp
                self._pending_whatsapp = None
                decision = CommandDecision(
                    action="open_whatsapp_message",
                    target=contact.name,
                    value=message,
                )
                return AssistantResult(
                    message=self.executor.execute(decision),
                    action=decision.action,
                    source="rules",
                )
            if normalised in {
                "no",
                "no thanks",
                "cancel",
                "cancel it",
                "don't",
                "do not",
                "nahi",
            }:
                self._pending_whatsapp = None
                decision = CommandDecision(action="cancel_whatsapp_message")
                return AssistantResult(
                    message=self.executor.execute(decision),
                    action=decision.action,
                    source="rules",
                )

            # A different command replaces the old pending request. This avoids
            # a later "yes" unexpectedly opening an outdated message.
            self._pending_whatsapp = None

        decision = self.rules.route(cleaned)
        source = "rules"

        if decision is None and self.gemini.available:
            try:
                decision = self.gemini.route(
                    cleaned,
                    allowed_sites=ALLOWED_SITES,
                    known_songs=music_library.music,
                )
                source = "gemini"
            except GeminiRoutingError as error:
                print(f"Gemini routing failed: {error}")

        if decision is None:
            decision = CommandDecision(
                action="unsupported",
                spoken_response="Sorry, try again.",
            )
            source = "fallback"

        if decision.action == "prepare_whatsapp_message":
            contact = self.executor.contacts.resolve(decision.target or "")
            message_text = (decision.value or "").strip()
            if contact is None:
                message = (
                    f"I don't know {decision.target or 'that contact'}. "
                    "Add the name and phone number to contacts.json first."
                )
            elif not message_text:
                message = (
                    f"Tell me the message for {contact.display_name} in the same "
                    "command."
                )
            else:
                self._pending_whatsapp = (contact, message_text)
                message = (
                    f"Your message to {contact.display_name} is: {message_text}. "
                    "Should I open it in WhatsApp?"
                )
            return AssistantResult(
                message=message,
                action=decision.action,
                source=source,
            )

        message = self.executor.execute(
            decision,
            defer_start_day_actions=defer_start_day_actions,
        )
        return AssistantResult(
            message=message,
            action=decision.action,
            source=source,
        )
