"""Persistent desktop microphone bridge for the local Flask dashboard."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from collections.abc import Callable

import speech_recognition as sr


VOICE_LANGUAGE = "en-IN"
VOICE_PAUSE_THRESHOLD = 1.35
VOICE_NON_SPEAKING_DURATION = 0.65
VOICE_PHRASE_THRESHOLD = 0.25
VOICE_PHRASE_TIME_LIMIT = 20
VOICE_OPERATION_TIMEOUT = 12
VOICE_MIN_ENERGY_THRESHOLD = 250
VOICE_MAX_ENERGY_THRESHOLD = 1000
WAKE_PHRASES = {
    "jarvis",
    "hey jarvis",
    "hello jarvis",
    "ok jarvis",
    "okay jarvis",
    "wake up jarvis",
}


def is_wake_phrase(transcript: str) -> bool:
    """Accept only a short wake phrase, not an arbitrary command mentioning Jarvis."""
    normalized = " ".join(re.sub(r"[^a-z]+", " ", transcript.casefold()).split())
    return normalized in WAKE_PHRASES


class DashboardVoiceSession:
    """Listen with the same Python speech pipeline used by ``main_02.py``.

    The background listener emits transcripts only. The browser remains
    responsible for displaying and submitting them through the normal command
    endpoint, so typed and spoken commands use exactly the same action path.
    """

    def __init__(
        self,
        transcript_selector: Callable[[list[str]], str] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = False
        self._paused = False
        self._standby = False
        self._state = "off"
        self._events: deque[dict[str, object]] = deque(maxlen=50)
        self._next_event_id = 1
        self._capture_generation = 0
        self._transcript_selector = transcript_selector

    def _select_google_transcript(self, result: dict[str, object]) -> str:
        if not isinstance(result, dict):
            return ""
        alternatives = result.get("alternative", [])
        candidates = [
            item["transcript"].strip()
            for item in alternatives
            if isinstance(item, dict)
            and isinstance(item.get("transcript"), str)
            and item["transcript"].strip()
        ]
        if not candidates:
            return ""
        with self._lock:
            standby = self._standby
        if standby:
            for candidate in candidates:
                if is_wake_phrase(candidate):
                    return candidate
        if self._transcript_selector is not None:
            return self._transcript_selector(candidates)
        return candidates[0]

    @property
    def available(self) -> bool:
        try:
            sr.Microphone.get_pyaudio()
        except (AttributeError, ImportError):
            return False
        return True

    def status(self) -> dict[str, object]:
        with self._lock:
            latest_event_id = (
                int(self._events[-1]["id"]) if self._events else 0
            )
            return {
                "enabled": self._enabled,
                "paused": self._paused,
                "standby": self._standby,
                "state": self._state,
                "latest_event_id": latest_event_id,
            }

    def start(self) -> dict[str, object]:
        if not self.available:
            raise RuntimeError("The Python microphone driver is unavailable.")

        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._enabled:
                    self._paused = False
                    self._standby = False
                    self._state = "listening"
                    return self.status_unlocked()
                raise RuntimeError("The microphone is still stopping. Try again.")

            self._stop_event = threading.Event()
            self._capture_generation += 1
            self._enabled = True
            self._paused = False
            self._standby = False
            self._state = "calibrating"
            self._thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name="jarvis-dashboard-voice",
            )
            self._thread.start()
            return self.status_unlocked()

    def stop(self) -> dict[str, object]:
        with self._lock:
            self._enabled = False
            self._paused = False
            self._standby = False
            self._state = "off"
            self._capture_generation += 1
            self._stop_event.set()
            return self.status_unlocked()

    def pause(self) -> dict[str, object]:
        with self._lock:
            if self._enabled:
                self._paused = True
                self._state = "paused"
                self._capture_generation += 1
            return self.status_unlocked()

    def resume(self) -> dict[str, object]:
        with self._lock:
            if self._enabled:
                self._paused = False
                self._state = "standby" if self._standby else "listening"
            return self.status_unlocked()

    def standby(self) -> dict[str, object]:
        """Keep the microphone alive but ignore everything except wake phrases."""
        with self._lock:
            if self._enabled and (not self._standby or self._paused):
                self._standby = True
                self._paused = False
                self._state = "standby"
                self._capture_generation += 1
            return self.status_unlocked()

    def events_after(self, event_id: int) -> list[dict[str, object]]:
        with self._lock:
            return [event.copy() for event in self._events if event["id"] > event_id]

    def status_unlocked(self) -> dict[str, object]:
        latest_event_id = int(self._events[-1]["id"]) if self._events else 0
        return {
            "enabled": self._enabled,
            "paused": self._paused,
            "standby": self._standby,
            "state": self._state,
            "latest_event_id": latest_event_id,
        }

    def _set_state(self, state: str) -> None:
        with self._lock:
            if self._enabled and (not self._paused or state == "paused"):
                self._state = state

    def _emit(self, event_type: str, **payload: object) -> None:
        with self._lock:
            event = {
                "id": self._next_event_id,
                "type": event_type,
                **payload,
            }
            self._next_event_id += 1
            self._events.append(event)

    def _handle_transcript(
        self,
        transcript: str,
        generation: int,
        *,
        audio_seconds: float | None = None,
        recognition_seconds: float | None = None,
    ) -> None:
        """Deliver commands when active, or only a wake event in standby."""
        with self._lock:
            if (
                self._paused
                or not self._enabled
                or self._capture_generation != generation
            ):
                return
            if self._standby and not is_wake_phrase(transcript):
                self._state = "standby"
                return
            waking = self._standby
            self._standby = False
            # Pause before browser speech so Jarvis cannot hear its own reply.
            self._paused = True
            self._state = "paused"
            self._capture_generation += 1
        if waking:
            self._emit("wake")
        else:
            self._emit(
                "transcript",
                transcript=transcript,
                audio_seconds=audio_seconds,
                recognition_seconds=recognition_seconds,
            )

    @staticmethod
    def _configure_recognizer(recognizer: sr.Recognizer) -> None:
        recognizer.pause_threshold = VOICE_PAUSE_THRESHOLD
        recognizer.non_speaking_duration = VOICE_NON_SPEAKING_DURATION
        recognizer.phrase_threshold = VOICE_PHRASE_THRESHOLD
        recognizer.operation_timeout = VOICE_OPERATION_TIMEOUT
        recognizer.dynamic_energy_threshold = True

    @staticmethod
    def _limit_energy_threshold(recognizer: sr.Recognizer) -> None:
        recognizer.energy_threshold = min(
            VOICE_MAX_ENERGY_THRESHOLD,
            max(VOICE_MIN_ENERGY_THRESHOLD, recognizer.energy_threshold),
        )

    def _capture_audio(
        self,
        recognizer: sr.Recognizer,
        generation: int,
    ) -> sr.AudioData | None:
        """Capture one phrase, then close the microphone before transcription."""

        with sr.Microphone() as source:
            while not self._stop_event.is_set():
                with self._lock:
                    if (
                        not self._enabled
                        or self._paused
                        or self._capture_generation != generation
                    ):
                        return None
                try:
                    return recognizer.listen(
                        source,
                        timeout=1,
                        phrase_time_limit=VOICE_PHRASE_TIME_LIMIT,
                    )
                except sr.WaitTimeoutError:
                    continue
        return None

    def _listen_loop(self) -> None:
        recognizer = sr.Recognizer()
        self._configure_recognizer(recognizer)

        unexpected_error: str | None = None
        try:
            # Calibrate in a short-lived stream. A brief startup noise can make
            # automatic calibration far too insensitive, so keep the result in
            # a practical range and let dynamic adjustment continue afterward.
            for attempt in range(3):
                try:
                    with sr.Microphone() as source:
                        self._set_state("calibrating")
                        recognizer.adjust_for_ambient_noise(source, duration=1.0)
                    break
                except (AttributeError, OSError):
                    if attempt == 2 or self._stop_event.is_set():
                        raise
                    self._stop_event.wait(0.4)
            self._limit_energy_threshold(recognizer)

            capture_errors = 0
            while not self._stop_event.is_set():
                with self._lock:
                    enabled = self._enabled
                    paused = self._paused
                    standby = self._standby
                    generation = self._capture_generation
                if not enabled:
                    break
                if paused:
                    self._stop_event.wait(0.08)
                    continue

                self._set_state("standby" if standby else "listening")
                try:
                    audio = self._capture_audio(recognizer, generation)
                except (AttributeError, OSError) as error:
                    # Windows can briefly close the headset stream when the
                    # audio device changes. Reopen it instead of silently
                    # ending the always-on listener.
                    capture_errors += 1
                    if capture_errors == 1 or capture_errors % 5 == 0:
                        self._emit(
                            "error",
                            message=f"Microphone disconnected; retrying: {error}",
                        )
                    self._set_state("reconnecting")
                    self._stop_event.wait(min(3.0, 0.4 * capture_errors))
                    continue
                capture_errors = 0
                if audio is None:
                    continue

                with self._lock:
                    if (
                        self._paused
                        or not self._enabled
                        or self._capture_generation != generation
                    ):
                        continue
                self._set_state("standby" if standby else "transcribing")

                try:
                    recognition_started = time.monotonic()
                    result = recognizer.recognize_google(
                        audio,
                        language=VOICE_LANGUAGE,
                        show_all=True,
                    )
                    recognition_seconds = time.monotonic() - recognition_started
                    transcript = self._select_google_transcript(result)
                except sr.UnknownValueError:
                    self._set_state("listening")
                    continue
                except TimeoutError:
                    # A temporary Google recognition timeout should not tear
                    # down always-on listening or create repeated error toasts.
                    self._set_state("listening")
                    continue
                except sr.RequestError as error:
                    self._emit(
                        "error",
                        message=f"Speech recognition is unavailable: {error}",
                    )
                    self._set_state("listening")
                    self._stop_event.wait(0.8)
                    continue

                if not transcript:
                    continue

                audio_seconds = len(audio.frame_data) / (
                    audio.sample_rate * audio.sample_width
                )
                self._handle_transcript(
                    transcript,
                    generation,
                    audio_seconds=round(audio_seconds, 2),
                    recognition_seconds=round(recognition_seconds, 2),
                )
        except (AttributeError, OSError) as error:
            unexpected_error = f"Microphone error: {error}"
        finally:
            if unexpected_error:
                self._emit("error", message=unexpected_error)
            with self._lock:
                if self._state != "off":
                    self._state = "error" if unexpected_error else "off"
                self._enabled = False
                self._paused = False
                self._standby = False
