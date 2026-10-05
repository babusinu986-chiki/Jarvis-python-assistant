"""Persistent desktop microphone bridge for the local Flask dashboard."""

from __future__ import annotations

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
        self._state = "off"
        self._events: deque[dict[str, object]] = deque(maxlen=50)
        self._next_event_id = 1
        self._capture_generation = 0
        self._transcript_selector = transcript_selector

    def _select_google_transcript(self, result: dict[str, object]) -> str:
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
                    self._state = "listening"
                    return self.status_unlocked()
                raise RuntimeError("The microphone is still stopping. Try again.")

            self._stop_event = threading.Event()
            self._capture_generation += 1
            self._enabled = True
            self._paused = False
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
                self._state = "listening"
            return self.status_unlocked()

    def events_after(self, event_id: int) -> list[dict[str, object]]:
        with self._lock:
            return [event.copy() for event in self._events if event["id"] > event_id]

    def status_unlocked(self) -> dict[str, object]:
        latest_event_id = int(self._events[-1]["id"]) if self._events else 0
        return {
            "enabled": self._enabled,
            "paused": self._paused,
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
            with sr.Microphone() as source:
                self._set_state("calibrating")
                recognizer.adjust_for_ambient_noise(source, duration=1.0)
            self._limit_energy_threshold(recognizer)

            while not self._stop_event.is_set():
                with self._lock:
                    enabled = self._enabled
                    paused = self._paused
                    generation = self._capture_generation
                if not enabled:
                    break
                if paused:
                    self._stop_event.wait(0.08)
                    continue

                self._set_state("listening")
                audio = self._capture_audio(recognizer, generation)
                if audio is None:
                    continue

                with self._lock:
                    if (
                        self._paused
                        or not self._enabled
                        or self._capture_generation != generation
                    ):
                        continue
                self._set_state("transcribing")

                try:
                    result = recognizer.recognize_google(
                        audio,
                        language=VOICE_LANGUAGE,
                        show_all=True,
                    )
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

                # Discard audio captured before a typed command, stop, or pause.
                # This prevents buffered Jarvis speech from becoming a command
                # after voice mode resumes.
                with self._lock:
                    if (
                        self._paused
                        or not self._enabled
                        or self._capture_generation != generation
                    ):
                        continue

                # Pause immediately so Jarvis never transcribes its own
                # browser-spoken response. The frontend resumes after reply.
                with self._lock:
                    self._paused = True
                    self._state = "paused"
                    self._capture_generation += 1
                self._emit("transcript", transcript=transcript)
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
