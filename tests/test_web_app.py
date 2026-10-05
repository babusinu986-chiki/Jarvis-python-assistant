from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import speech_recognition as sr

from jarvis_ai.dashboard_voice import (
    VOICE_MAX_ENERGY_THRESHOLD,
    VOICE_MIN_ENERGY_THRESHOLD,
    VOICE_OPERATION_TIMEOUT,
    VOICE_PAUSE_THRESHOLD,
    VOICE_PHRASE_TIME_LIMIT,
    DashboardVoiceSession,
)
from web_app import create_app


class FakeVoiceSession:
    available = True

    def __init__(self) -> None:
        self.enabled = False
        self.paused = False

    def status(self):
        return {
            "enabled": self.enabled,
            "paused": self.paused,
            "state": "paused" if self.paused else ("listening" if self.enabled else "off"),
            "latest_event_id": 1 if self.enabled else 0,
        }

    def start(self):
        self.enabled = True
        self.paused = False
        return self.status()

    def stop(self):
        self.enabled = False
        self.paused = False
        return self.status()

    def pause(self):
        self.paused = self.enabled
        return self.status()

    def resume(self):
        self.paused = False
        return self.status()

    def events_after(self, event_id: int):
        if self.enabled and event_id < 1:
            return [{"id": 1, "type": "transcript", "transcript": "open YouTube"}]
        return []


class DashboardApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.voice = FakeVoiceSession()
        app = create_app(
            data_dir=Path(self.temp_dir.name),
            dry_run=True,
            voice_session=self.voice,
        )
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_and_health_load(self) -> None:
        page = self.client.get("/")
        health = self.client.get("/api/health")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Jarvis AI Assistant", page.data)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ready")

    def test_command_endpoint_runs_local_commands(self) -> None:
        response = self.client.post(
            "/api/command",
            json={"command": "what time is it"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["action"], "get_time")
        self.assertEqual(data["source"], "rules")

    def test_start_day_endpoint_defers_actions_until_briefing_finishes(self) -> None:
        response = self.client.post(
            "/api/command",
            json={"command": "start my day"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["action"], "start_my_day")
        self.assertIn("Good morning", data["message"])
        self.assertNotIn("I would open WhatsApp and LinkedIn", data["message"])
        self.assertEqual(
            data["follow_up"]["action"],
            "complete_start_my_day",
        )

        completion = self.client.post(
            "/api/start-day/complete",
            json={"token": data["follow_up"]["token"]},
        )
        repeated = self.client.post(
            "/api/start-day/complete",
            json={"token": data["follow_up"]["token"]},
        )

        self.assertEqual(completion.status_code, 200)
        self.assertIn(
            "I would open WhatsApp and LinkedIn",
            completion.get_json()["message"],
        )
        self.assertEqual(repeated.status_code, 409)

    def test_reminder_endpoints_add_list_and_remove(self) -> None:
        added = self.client.post(
            "/api/reminders",
            json={"text": "Practice my demo"},
        )
        listed = self.client.get("/api/reminders")
        removed = self.client.delete("/api/reminders/0")

        self.assertEqual(added.status_code, 201)
        self.assertEqual(listed.get_json()["reminders"], ["Practice my demo"])
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(
            self.client.get("/api/reminders").get_json()["reminders"],
            [],
        )

    def test_empty_command_is_rejected(self) -> None:
        response = self.client.post("/api/command", json={"command": "  "})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_exit_is_local_and_unknown_reply_is_short(self) -> None:
        exit_response = self.client.post(
            "/api/command",
            json={"command": "exit"},
        )
        unknown_response = self.client.post(
            "/api/command",
            json={"command": "flibbertigibbet command"},
        )

        self.assertEqual(exit_response.get_json()["action"], "sleep_mode")
        self.assertEqual(exit_response.get_json()["message"], "Going to sleep.")
        self.assertEqual(unknown_response.get_json()["message"], "Sorry, try again.")

    def test_desktop_voice_start_events_pause_resume_and_stop(self) -> None:
        started = self.client.post("/api/voice/start")
        events = self.client.get("/api/voice/events?after=0")
        paused = self.client.post("/api/voice/pause")
        resumed = self.client.post("/api/voice/resume")
        stopped = self.client.post("/api/voice/stop")

        self.assertTrue(started.get_json()["enabled"])
        self.assertEqual(
            events.get_json()["events"][0]["transcript"],
            "open YouTube",
        )
        self.assertTrue(paused.get_json()["paused"])
        self.assertFalse(resumed.get_json()["paused"])
        self.assertFalse(stopped.get_json()["enabled"])


class DashboardVoiceConfigurationTests(unittest.TestCase):
    def test_google_alternatives_can_be_selected_without_another_api_call(self) -> None:
        session = DashboardVoiceSession(transcript_selector=lambda items: items[-1])
        transcript = session._select_google_transcript(
            {"alternative": [
                {"transcript": "open you to"},
                {"transcript": "open YouTube"},
            ]}
        )
        self.assertEqual(transcript, "open YouTube")

    def test_recognizer_allows_natural_pauses_and_longer_commands(self) -> None:
        recognizer = sr.Recognizer()

        DashboardVoiceSession._configure_recognizer(recognizer)

        self.assertEqual(recognizer.pause_threshold, VOICE_PAUSE_THRESHOLD)
        self.assertGreaterEqual(recognizer.pause_threshold, 1.3)
        self.assertEqual(recognizer.operation_timeout, VOICE_OPERATION_TIMEOUT)
        self.assertEqual(VOICE_PHRASE_TIME_LIMIT, 20)

    def test_calibrated_energy_threshold_is_kept_in_practical_range(self) -> None:
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 5000
        DashboardVoiceSession._limit_energy_threshold(recognizer)
        self.assertEqual(recognizer.energy_threshold, VOICE_MAX_ENERGY_THRESHOLD)

        recognizer.energy_threshold = 10
        DashboardVoiceSession._limit_energy_threshold(recognizer)
        self.assertEqual(recognizer.energy_threshold, VOICE_MIN_ENERGY_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
