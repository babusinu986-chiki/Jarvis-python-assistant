"""Allow-listed local actions for the Jarvis assistant."""

from __future__ import annotations

import os
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus, urlencode

import requests

import music_library

from .memory import MemoryStore
from .models import CommandDecision
from .reminders import ReminderStore
from .contacts import ContactStore
from .system_control import WindowsMediaController
from .weather import WeatherService, WeatherServiceError


ALLOWED_SITES = {
    "facebook": "https://www.facebook.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "youtube": "https://www.youtube.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org/k/",
}

SITE_DISPLAY_NAMES = {
    "facebook": "Facebook",
    "github": "GitHub",
    "google": "Google",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
}

SITE_ALIASES = {
    "facebook": "facebook",
    "github": "github",
    "google": "google",
    "instagram": "instagram",
    "linkedin": "linkedin",
    "linked in": "linkedin",
    "youtube": "youtube",
    "you tube": "youtube",
    "whatsapp": "whatsapp",
    "whats app": "whatsapp",
    "telegram": "telegram",
}


class ActionExecutor:
    def __init__ (
        self,
        memory: MemoryStore,
        *,
        reminders: ReminderStore | None = None,
        dry_run: bool = False,
        system_controller: WindowsMediaController | None = None,
        weather_service: WeatherService | None = None,
        contacts: ContactStore | None = None,
    ) -> None:
        self.memory = memory
        self.reminders = reminders or ReminderStore(
            memory.path.parent / "data" / "reminders.json"
        )
        self.dry_run = dry_run
        self.system_controller = system_controller or WindowsMediaController(
            dry_run=dry_run
        )
        self.weather_service = weather_service or WeatherService()
        self.contacts = contacts or ContactStore(memory.path.parent / "contacts.json")
        self.default_city = os.getenv("DEFAULT_CITY", "Goa").strip() or "Goa"

    def _open(self, url: str) -> None:
        if not self.dry_run:
            webbrowser.open(url)

    def execute(
        self,
        decision: CommandDecision,
        *,
        defer_start_day_actions: bool = False,
    ) -> str:
        action = decision.action

        if action == "open_website":
            site = (decision.target or "").lower().strip()
            url = ALLOWED_SITES.get(site)
            if not url:
                return "I can only open websites from my approved list."
            self._open(url)
            return f"Opening {SITE_DISPLAY_NAMES[site]}."

        if action == "web_search":
            query = (decision.target or "").strip()
            if not query:
                return "Tell me what you want to search for."
            self._open(f"https://www.google.com/search?q={quote_plus(query)}")
            return f"Searching the web for {query}."

        if action == "play_song":
            return self._play_song(decision.target or "")

        if action == "play_favorite_song":
            favorite_song = self.memory.get("favorite_song")
            if favorite_song is None:
                return (
                    "I do not have a favorite song saved yet. Say, remember my "
                    "favorite song is Skyfall."
                )
            return self._play_song(favorite_song)

        if action == "media_pause":
            if self.system_controller.toggle_playback():
                return "Pausing playback."
            return "Media control is available only on Windows."

        if action == "media_play":
            if self.system_controller.toggle_playback():
                return "Resuming playback."
            return "Media control is available only on Windows."

        if action == "navigate_back":
            if self.system_controller.go_back():
                return "Going back."
            return "Back control is available only on Windows."

        if action == "close_tab":
            if self.system_controller.close_tab():
                return "Closing the current browser tab."
            return "Tab control is available only on Windows."

        if action == "close_window":
            if self.system_controller.close_window():
                return "Closing the current window."
            return "Window control is available only on Windows."

        if action == "get_news":
            return self._get_news()

        if action == "get_time":
            now = datetime.now().astimezone()
            return f"The current time is {now.strftime('%I:%M %p').lstrip('0')}."

        if action == "get_date":
            today = datetime.now().astimezone()
            return (
                f"Today is {today.strftime('%A')}, {today.day} "
                f"{today.strftime('%B %Y')}."
            )

        if action == "get_weather":
            city = (decision.target or self.default_city).strip()
            if self.dry_run:
                return f"Dry run: I would fetch the current weather for {city}."
            try:
                return self.weather_service.current_summary(city)
            except WeatherServiceError as error:
                return str(error)

        if action == "add_reminder":
            reminder = (decision.target or "").strip()
            if not reminder:
                return "Tell me what you want to be reminded about."
            try:
                saved = self.reminders.add(reminder)
            except ValueError:
                return "Tell me what you want to be reminded about."
            return f"Reminder saved: {saved}."

        if action == "list_reminders":
            return self.reminders.spoken_summary()

        if action == "sleep_mode":
            return "Going to sleep."

        if action == "open_whatsapp_message":
            contact = self.contacts.resolve(decision.target or "")
            message = (decision.value or "").strip()
            if not contact:
                return "I could not find that contact."
            if not message:
                return "Tell me the message you want to prepare."
            url = f"https://wa.me/{contact.phone}?{urlencode({'text': message})}"
            self._open(url)
            if self.dry_run:
                return (
                    f"I would open WhatsApp for {contact.display_name} with the "
                    "message ready."
                )
            return (
                f"Opening WhatsApp for {contact.display_name} with the message "
                "ready. Review it and press Send."
            )

        if action == "cancel_whatsapp_message":
            return "Okay, I cancelled the WhatsApp message."

        if action == "start_my_day":
            return self._start_my_day(defer_actions=defer_start_day_actions)

        if action == "remember":
            key = (decision.target or "").strip()
            value = (decision.value or "").strip()
            if not key or not value:
                return "Tell me both what to remember and its value."
            self.memory.save(key, value)
            return decision.spoken_response or f"I will remember {key}."

        if action == "recall":
            key = (decision.target or "").strip()
            value = self.memory.get(key)
            if value is None:
                return f"I do not have anything saved for {key or 'that'} yet."
            return f"I remember that your {key.replace('_', ' ')} is {value}."

        if action in {"chat", "unsupported"}:
            return decision.spoken_response or (
                "I cannot safely handle that request yet."
                if action == "unsupported"
                else "I am listening."
            )

        return "I cannot safely handle that request yet."

    def _play_song(self, requested_song: str) -> str:
        song = requested_song.lower().strip()
        url = music_library.music.get(song)
        if not url:
            return f"I could not find {song or 'that song'} in the local music library."
        self._open(url)
        return f"Playing {song}."

    def _start_my_day(self, *, defer_actions: bool = False) -> str:
        name = self.memory.get("name")
        greeting = f"Good morning, {name}." if name else "Good morning."
        today = datetime.now().astimezone()
        date_and_time = (
            f"Today is {today.strftime('%A')}, {today.day} "
            f"{today.strftime('%B %Y')}, and the time is "
            f"{today.strftime('%I:%M %p').lstrip('0')}."
        )

        weather_result = self.execute(
            CommandDecision(action="get_weather", target=self.default_city)
        )
        news_result = self._get_news()
        reminder_result = self.reminders.spoken_summary()

        briefing = " ".join(
            (
                greeting,
                date_and_time,
                weather_result,
                news_result,
                reminder_result,
            )
        )
        if defer_actions:
            return (
                f"{briefing} After this briefing, I will prepare your workspace "
                "and start your favorite music."
            )

        return f"{briefing} {self.complete_start_my_day()}"

    def complete_start_my_day(self) -> str:
        """Open morning sites and music after the spoken briefing has finished."""

        opened: list[str] = []
        for site in ("whatsapp", "linkedin"):
            try:
                self._open(ALLOWED_SITES[site])
                opened.append(SITE_DISPLAY_NAMES[site])
            except (OSError, webbrowser.Error):
                continue

        if opened:
            if self.dry_run:
                website_result = f"I would open {' and '.join(opened)}."
            else:
                website_result = f"I have opened {' and '.join(opened)}."
        else:
            website_result = "I could not open WhatsApp or LinkedIn."

        favorite_song = self.memory.get("favorite_song")
        if favorite_song:
            song_result = self._play_song(favorite_song)
            if self.dry_run and song_result.startswith("Playing "):
                song_result = song_result.replace("Playing ", "I would play ", 1)
        else:
            song_result = "You do not have a favorite song saved yet."

        return f"{website_result} {song_result}"

    def _get_news(self) -> str:
        if self.dry_run:
            return "Dry run: I would fetch the latest Indian news headlines."

        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            return "News is not configured. Add NEWS_API_KEY to the .env file."

        try:
            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": "India",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "apiKey": api_key,
                    "pageSize": 5,
                },
                timeout=10,
            )
            data = response.json()
            if response.status_code == 401 and data.get("code") == "apiKeyInvalid":
                return "NewsAPI rejected the API key. Replace NEWS_API_KEY in the .env file."
            if response.status_code == 429:
                return "The NewsAPI request limit has been reached. Try again later."
            response.raise_for_status()
            articles = data.get("articles", [])
        except (requests.RequestException, ValueError, AttributeError):
            return "I could not reach the news service right now."

        titles = [article.get("title", "").strip() for article in articles]
        titles = [
            title
            for title in titles
            if title and title.lower() != "[removed]"
        ]
        if not titles:
            return "NewsAPI is working, but it returned no current India headlines."
        return "Here are the latest India-related headlines. " + " Next: ".join(
            titles[:3]
        )
