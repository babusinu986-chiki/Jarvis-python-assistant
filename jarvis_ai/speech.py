"""Low-latency text-to-speech with persistent gTTS audio caching."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import pyttsx3
from gtts import gTTS


class Speaker:
    """Speak with cached gTTS audio, falling back to Windows offline speech."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        cache_dir: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.cache_dir = cache_dir or (
            Path(__file__).resolve().parents[1] / "data" / "voice_cache"
        )
        self._offline_engine = None

        if self.enabled and pygame.mixer.get_init() is None:
            pygame.mixer.init()

    def say(self, text: str) -> None:
        if not self.enabled or not text:
            return

        try:
            audio_path = self._ensure_gtts_audio(text)
            self._play(audio_path)
            return
        except Exception as error:
            print(f"Google voice playback failed; using Windows voice: {error}")

        try:
            self._say_with_windows_voice(text)
        except Exception as error:
            print(f"Text-to-speech is unavailable: {error}")

    def prepare(self, lines: Iterable[str]) -> tuple[int, int, int]:
        """Cache common voice lines without playing them.

        Returns (newly_generated, already_cached, failed). Stop after the first
        network failure so an unavailable gTTS service cannot hold up startup.
        """
        generated = 0
        cached = 0
        failed = 0
        unique_lines = list(
            dict.fromkeys(text.strip() for text in lines if text.strip())
        )
        for index, line in enumerate(unique_lines):
            path = self._cache_path(line)
            if path.exists() and path.stat().st_size > 0:
                cached += 1
                continue
            try:
                self._ensure_gtts_audio(line)
            except Exception as error:
                failed = len(unique_lines) - index
                print(f"Voice cache download stopped: {error}")
                break
            generated += 1
        return generated, cached, failed

    def _cache_path(self, text: str) -> Path:
        digest = hashlib.sha256(f"en\0{text}".encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{digest}.mp3"

    def _ensure_gtts_audio(self, text: str) -> Path:
        """Return cached audio, generating it once when necessary."""
        destination = self._cache_path(text)
        if destination.exists() and destination.stat().st_size > 0:
            return destination

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".mp3",
            dir=self.cache_dir,
            delete=False,
        )
        temporary_path = Path(temporary_file.name)
        temporary_file.close()

        try:
            gTTS(text=text, lang="en", timeout=5).save(str(temporary_path))
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)

        return destination

    @staticmethod
    def _play(audio_path: Path) -> None:
        pygame.mixer.music.load(str(audio_path))
        pygame.mixer.music.play()
        clock = pygame.time.Clock()
        while pygame.mixer.music.get_busy():
            clock.tick(20)
        pygame.mixer.music.unload()

    def _say_with_windows_voice(self, text: str) -> None:
        """Use pyttsx3 only when online speech generation or playback fails."""
        if self._offline_engine is None:
            self._offline_engine = pyttsx3.init()
            self._offline_engine.setProperty("rate", 180)
        self._offline_engine.say(text)
        self._offline_engine.runAndWait()
