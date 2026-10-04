"""High-level orchestration for command routing and execution."""

from __future__ import annotations

from pathlib import Path

import music_library

from .actions import ALLOWED_SITES, SITE_ALIASES, ActionExecutor
from .memory import MemoryStore
from .models import AssistantResult, CommandDecision
from .router import GeminiRouter, GeminiRoutingError, RuleRouter


class JarvisAssistant:
    def __init__(self, data_dir: Path, *, dry_run: bool = False) -> None:
        memory = MemoryStore(data_dir / "memory.json")
        self.rules = RuleRouter(SITE_ALIASES, music_library.music)
        self.gemini = GeminiRouter()
        self.executor = ActionExecutor(memory, dry_run=dry_run)

    @property
    def ai_available(self) -> bool:
        return self.gemini.available

    def handle(self, command: str) -> AssistantResult:
        cleaned = command.strip()
        if not cleaned:
            return AssistantResult(
                message="Please say or type a command.",
                action="unsupported",
                source="fallback",
            )

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
                spoken_response=(
                    "I do not recognize that command yet. Configure Gemini to enable "
                    "more flexible natural-language requests."
                ),
            )
            source = "fallback"

        message = self.executor.execute(decision)
        return AssistantResult(
            message=message,
            action=decision.action,
            source=source,
        )
