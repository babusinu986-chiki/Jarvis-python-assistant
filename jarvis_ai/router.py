"""Deterministic routing plus optional Gemini structured intent parsing."""

from __future__ import annotations

import os
import queue
import re
import threading
from collections.abc import Iterable

from google import genai

from .models import CommandDecision


class GeminiRoutingError(RuntimeError):
    """Raised when Gemini cannot return a valid routing decision."""


class RuleRouter:
    """Handle obvious commands locally for speed and offline use."""

    def __init__(
        self,
        site_aliases: dict[str, str],
        known_songs: Iterable[str] = (),
    ) -> None:
        self.site_aliases = site_aliases
        self.known_songs = {
            " ".join(song.lower().split()): song
            for song in known_songs
        }

    def route(self, raw_command: str) -> CommandDecision | None:
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
            return CommandDecision(action="close_window")

        if command in {"previous page", "browser back", "navigate back"}:
            return CommandDecision(action="navigate_back")

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
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
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
You are the intent router for a desktop voice assistant. Convert the user's
request into exactly one safe structured action. Never claim that an action
has already happened. Do not create actions outside the schema.

Allowed website targets: {sites}
Known local song targets: {songs}

Routing rules:
- open_website: only when the target exactly matches an allowed website key.
- web_search: for requests to search the web; target is only the search query.
- play_song: only for a known local song target.
- play_favorite_song: when the user asks to play the saved favorite song.
- media_pause: when the user wants current audio or video playback paused.
- media_play: when the user wants current audio or video playback resumed.
- navigate_back: when the user asks the foreground app or browser to go back.
- close_window: when the user explicitly asks to close the foreground window.
- get_news: for current news requests.
- get_time: for the current local computer time; target is empty.
- get_date: for the current local computer date; target is empty.
- get_weather: for weather or rain questions; target is the city when provided.
- remember: target is a short memory key and value is the information to save.
- recall: target is a short memory key.
- chat: answer harmless general conversation in at most two short sentences.
- unsupported: requests involving arbitrary programs, files, credentials,
  purchases, messages, system settings, code execution, or unclear intent.

For chat and unsupported, put the response in spoken_response. Keep every
spoken_response concise and honest.

User request: {command!r}
""".strip()

        try:
            interaction = self._request_with_deadline(prompt)
            return CommandDecision.model_validate_json(interaction.output_text)
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
                result = self._client.interactions.create(
                    model=self.model,
                    input=prompt,
                    timeout=min(self.timeout_seconds, 5.0),
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": CommandDecision.model_json_schema(),
                    },
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
