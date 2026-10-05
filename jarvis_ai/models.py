"""Typed command models shared by the router and action executor."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ActionName = Literal[
    "open_website",
    "web_search",
    "play_song",
    "play_favorite_song",
    "media_pause",
    "media_play",
    "navigate_back",
    "close_tab",
    "close_window",
    "get_news",
    "get_time",
    "get_date",
    "get_weather",
    "start_my_day",
    "add_reminder",
    "list_reminders",
    "sleep_mode",
    "prepare_whatsapp_message",
    "open_whatsapp_message",
    "cancel_whatsapp_message",
    "remember",
    "recall",
    "chat",
    "unsupported",
]


class CommandDecision(BaseModel):
    """A validated plan produced by rules or Gemini."""

    action: ActionName
    target: str | None = Field(
        default=None,
        description=(
            "A site key, search query, song title, city name, or memory key."
        ),
    )
    value: str | None = Field(
        default=None,
        description="The value to store when the action is remember.",
    )
    spoken_response: str = Field(
        default="",
        max_length=400,
        description="A short response suitable for speaking aloud.",
    )


class AssistantResult(BaseModel):
    """Final result returned to the CLI or voice interface."""

    message: str
    action: ActionName
    source: Literal["rules", "gemini", "fallback"]
