"""Deterministic routing plus optional Gemini structured intent parsing."""

from __future__ import annotations

import os
import queue
import re
import threading
from collections.abc import Iterable

from google import genai
from google.genai import types

from .models import CommandDecision


class GeminiRoutingError(RuntimeError):
    """Raised when Gemini cannot return a valid routing decision."""


class RuleRouter:
    """Handle obvious commands locally for speed and offline use."""

    def __init__(
        self,
        site_aliases: dict[str, str],
        known_songs: Iterable[str] = (),
        contact_aliases: dict[str, str] | None = None,
    ) -> None:
        self.site_aliases = site_aliases
        self.known_songs = {
            " ".join(song.lower().split()): song
            for song in known_songs
        }
        self.contact_aliases = contact_aliases or {}

    def _route_whatsapp_message(
        self,
        raw_command: str,
    ) -> CommandDecision | None:
        """Parse a contact-first WhatsApp request without sending anything."""

        command = " ".join(raw_command.strip().split())
        prefix_patterns = (
            r"^(?:please\s+)?(?:send|write)(?:\s+a)?(?:\s+whatsapp)?"
            r"\s+message\s+to\s+(.+)$",
            r"^(?:please\s+)?(?:message|text)\s+(.+)$",
        )

        payload: str | None = None
        for pattern in prefix_patterns:
            match = re.fullmatch(pattern, command, flags=re.IGNORECASE)
            if match:
                payload = match.group(1).strip()
                break
        if payload is None:
            return None

        aliases = sorted(self.contact_aliases, key=len, reverse=True)
        for alias in aliases:
            contact_match = re.match(
                rf"^{re.escape(alias)}(?=$|[\s,:-])",
                payload,
                flags=re.IGNORECASE,
            )
            if not contact_match:
                continue

            message = payload[contact_match.end():].lstrip(" ,:-")
            message = re.sub(
                r"^(?:saying|says|that\s+says|with\s+(?:the\s+)?message|message|that)"
                r"\s*[:,-]?\s*",
                "",
                message,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            return CommandDecision(
                action="prepare_whatsapp_message",
                target=self.contact_aliases[alias],
                value=message or None,
            )

        # Also understand: "send message Hello, I am coming to Bablu" and the
        # common spoken variation "send message to Hello ... to Bablu".
        for alias in aliases:
            trailing_contact = re.search(
                rf"\s+to\s+{re.escape(alias)}$",
                payload,
                flags=re.IGNORECASE,
            )
            if trailing_contact:
                message = payload[:trailing_contact.start()].strip(" ,:-")
                return CommandDecision(
                    action="prepare_whatsapp_message",
                    target=self.contact_aliases[alias],
                    value=message or None,
                )

        requested_name, _, message = payload.partition(" ")
        return CommandDecision(
            action="prepare_whatsapp_message",
            target=requested_name,
            value=message.strip() or None,
        )

    def route(self, raw_command: str) -> CommandDecision | None:
        whatsapp_message = self._route_whatsapp_message(raw_command)
        if whatsapp_message is not None:
            return whatsapp_message

        command = " ".join(raw_command.lower().split())
        command = re.sub(r"[.!?]+$", "", command).strip()

        name_match = re.fullmatch(r"remember my name is (.+)", command)
        if name_match:
            value = name_match.group(1).strip().title()
            return CommandDecision(
                action="remember",
                target="name",
                value=value,
                spoken_response=f"I will remember your name as {value}.",
            )

        song_patterns = (
            r"remember(?: that)? my favou?rite song (?:is|as) (.+)",
            r"(?:save|set) (.+) as my favou?rite song",
            r"my favou?rite song is (.+)",
        )
        for pattern in song_patterns:
            song_match = re.fullmatch(pattern, command)
            if song_match:
                value = song_match.group(1).strip(" .!?\"'")
                if value:
                    return CommandDecision(
                        action="remember",
                        target="favorite_song",
                        value=value,
                        spoken_response=(
                            f"I will remember {value} as your favorite song."
                        ),
                    )

        incomplete_song_memory_commands = {
            "remember my favorite song",
            "remember my favorite song is",
            "remember my favourite song",
            "remember my favourite song is",
            "save my favorite song",
            "save my favourite song",
        }
        if command in incomplete_song_memory_commands:
            return CommandDecision(
                action="unsupported",
                spoken_response=(
                    "Tell me the song name. For example, remember my favorite "
                    "song is Skyfall."
                ),
            )

        if command in {
            "what is my name",
            "what's my name",
            "whats my name",
            "tell me my name",
            "do you remember my name",
            "who am i",
        }:
            return CommandDecision(action="recall", target="name")

        if command in {
            "what is my favorite song",
            "what's my favorite song",
            "whats my favorite song",
            "tell me my favorite song",
            "do you remember my favorite song",
        }:
            return CommandDecision(action="recall", target="favorite_song")

        if command in {
            "play my favorite song",
            "play favorite song",
            "play my favourite song",
            "play favourite song",
        }:
            return CommandDecision(action="play_favorite_song")

        if command in {
            "start my day",
            "begin my day",
            "good morning jarvis",
            "give me my morning briefing",
            "morning briefing",
            "give me my daily briefing",
            "daily briefing",
        }:
            return CommandDecision(action="start_my_day")

        reminder_match = re.fullmatch(
            r"(?:remind me to|add (?:a )?reminder(?: to)?|set (?:a )?reminder(?: to)?|remember to) (.+)",
            command,
        )
        if reminder_match:
            return CommandDecision(
                action="add_reminder",
                target=reminder_match.group(1).strip(),
            )

        if command in {
            "what are my reminders",
            "tell me my reminders",
            "read my reminders",
            "list my reminders",
            "my reminders",
        }:
            return CommandDecision(action="list_reminders")

        if command in {
            "exit",
            "quit",
            "sleep",
            "sleep mode",
            "go to sleep",
            "stop listening",
            "stop voice mode",
            "turn off voice mode",
            "jarvis sleep",
            "shutdown jarvis",
        }:
            return CommandDecision(action="sleep_mode")

        if command in {
            "pause",
            "pause music",
            "pause the music",
            "pause playback",
            "stop playback",
            "ruk jao",
            "ruko",
            "gana roko",
            "music roko",
        }:
            return CommandDecision(action="media_pause")

        if command in {
            "play",
            "resume",
            "resume music",
            "resume playback",
            "continue",
            "play karo",
            "chalu karo",
            "gana chalao",
        }:
            return CommandDecision(action="media_play")

        if command in {
            "back",
            "go back",
            "go back please",
            "back jao",
            "piche jao",
            "peeche jao",
            "wapas jao",
        }:
            return CommandDecision(action="navigate_back")

        if command in {"previous page", "browser back", "navigate back"}:
            return CommandDecision(action="navigate_back")

        if command in {
            "close tab",
            "close this tab",
            "close current tab",
            "close page",
            "close this page",
            "close webpage",
            "cancel this page",
            "tab band karo",
            "page band karo",
        }:
            return CommandDecision(action="close_tab")

        if command in {
            "close window",
            "close this window",
            "close current window",
        }:
            return CommandDecision(action="close_window")

        if re.search(r"\b(?:news|headlines)\b", command) or command in {
            "aaj ki khabar",
            "khabar batao",
        }:
            return CommandDecision(action="get_news")

        if command in {
            "what time is it",
            "what is the time",
            "what's the time",
            "whats the time",
            "tell me the time",
            "tell me current time",
            "current time",
            "time please",
            "time kya hai",
            "samay kya hai",
            "time",
        }:
            return CommandDecision(action="get_time")

        if command in {
            "what is today's date",
            "what is todays date",
            "what is the date",
            "tell me the date",
            "today's date",
            "todays date",
            "current date",
            "what day is it",
            "aaj ki date kya hai",
            "date kya hai",
            "aaj kaun sa din hai",
        }:
            return CommandDecision(action="get_date")

        weather_trigger = re.search(
            r"\b(?:weather|temperature|forecast|rain|raining|mausam)\b",
            command,
        )
        if weather_trigger:
            city: str | None = None
            city_match = re.search(r"\b(?:in|at|for|of)\s+(.+)$", command)
            if city_match:
                city = re.sub(
                    r"\s+(?:today|now|right now)$",
                    "",
                    city_match.group(1),
                ).strip()
            elif command not in {
                "aaj ka mausam",
                "aaj ka mausam kaisa hai",
                "mausam kaisa hai",
            }:
                hindi_city_match = re.fullmatch(
                    r"(.+?) ka mausam(?: kaisa hai)?",
                    command,
                )
                if hindi_city_match:
                    city = hindi_city_match.group(1).strip()
            return CommandDecision(action="get_weather", target=city or None)

        search_match = re.search(
            r"(?:search(?: the web)?|google|look up|find online) (?:for )?(.+)",
            command,
        )
        if search_match:
            return CommandDecision(action="web_search", target=search_match.group(1))

        play_match = re.fullmatch(r"play (.+)", command)
        if play_match:
            return CommandDecision(action="play_song", target=play_match.group(1))

        if command in self.known_songs:
            return CommandDecision(
                action="play_song",
                target=self.known_songs[command],
            )

        for alias, site_key in self.site_aliases.items():
            if command == f"open {alias}":
                return CommandDecision(action="open_website", target=site_key)

        site_triggers = ("open", "launch", "take me to", "go to", "visit")
        if any(trigger in command for trigger in site_triggers):
            for alias, site_key in self.site_aliases.items():
                if re.search(rf"\b{re.escape(alias)}\b", command):
                    return CommandDecision(action="open_website", target=site_key)

        return None


class GeminiRouter:
    """Use Gemini structured output to understand flexible commands safely."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.timeout_seconds = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "5"))
        self._client = genai.Client(api_key=self.api_key) if self.api_key else None

    @property
    def available(self) -> bool:
        return self._client is not None

    def route(
        self,
        command: str,
        *,
        allowed_sites: Iterable[str],
        known_songs: Iterable[str],
    ) -> CommandDecision:
        if not self._client:
            raise GeminiRoutingError("GEMINI_API_KEY is not configured.")

        sites = ", ".join(sorted(allowed_sites))
        songs = ", ".join(sorted(known_songs)) or "none"
        prompt = f"""
Route one desktop voice request to exactly one schema action. Never claim an
action happened. For open_website, target must be one of: {sites}.
For play_song, target must be one of: {songs}. For web_search, target is only
the search query; for get_weather, target is only the city. Use chat for a
harmless general question and answer it in spoken_response in at most two
short sentences. Use unsupported for unclear requests or arbitrary programs,
files, credentials, purchases, messages, system settings, or code execution.
For chat and unsupported, always provide a concise spoken_response.
Request: {command!r}
""".strip()

        try:
            interaction = self._request_with_deadline(prompt)
            return CommandDecision.model_validate_json(interaction.text)
        except Exception as error:
            raise GeminiRoutingError(str(error)) from error

    def _request_with_deadline(self, prompt: str):
        """Run the SDK request on a daemon thread with a hard app deadline.

        The SDK can retry internally beyond its transport timeout. A daemon thread
        ensures a weak connection cannot freeze the assistant's main voice loop.
        """
        if not self._client:
            raise GeminiRoutingError("GEMINI_API_KEY is not configured.")

        result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

        def request() -> None:
            try:
                result = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=CommandDecision,
                    ),
                )
                result_queue.put((True, result))
            except Exception as error:
                result_queue.put((False, error))

        threading.Thread(target=request, daemon=True, name="gemini-router").start()

        try:
            succeeded, result = result_queue.get(timeout=self.timeout_seconds)
        except queue.Empty as error:
            raise GeminiRoutingError(
                f"Gemini did not respond within {self.timeout_seconds:g} seconds."
            ) from error

        if not succeeded:
            raise GeminiRoutingError(str(result))
        return result
