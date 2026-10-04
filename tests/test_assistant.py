from __future__ import annotations

import tempfile
import time
import unittest
from unittest.mock import Mock, call, patch
from pathlib import Path

from jarvis_ai.actions import SITE_ALIASES, ActionExecutor
from jarvis_ai.memory import MemoryStore
from jarvis_ai.models import CommandDecision
from jarvis_ai.router import GeminiRouter, RuleRouter
from jarvis_ai.speech import Speaker
from jarvis_ai.system_control import WindowsMediaController


class FakeInteraction:
    output_text = (
        '{"action":"open_website","target":"linkedin","value":null,'
        '"spoken_response":""}'
    )


class FakeInteractions:
    def __init__(self) -> None:
        self.last_request = None

    def create(self, **request):
        self.last_request = request
        return FakeInteraction()


class FakeGeminiClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()


class SlowInteractions:
    def create(self, **_request):
        time.sleep(0.2)
        return FakeInteraction()


class SlowGeminiClient:
    def __init__(self) -> None:
        self.interactions = SlowInteractions()


class RuleRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = RuleRouter(SITE_ALIASES, {"skyfall", "this"})

    def test_routes_known_website(self) -> None:
        decision = self.router.route("open YouTube")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "open_website")
        self.assertEqual(decision.target, "youtube")

    def test_routes_whatsapp_locally(self) -> None:
        decision = self.router.route("open WhatsApp")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "open_website")
        self.assertEqual(decision.target, "whatsapp")

    def test_routes_web_search(self) -> None:
        decision = self.router.route("search for voice assistant architecture")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "web_search")
        self.assertEqual(decision.target, "voice assistant architecture")

    def test_routes_flexible_website_phrase_locally(self) -> None:
        decision = self.router.route("could you take me to LinkedIn please")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "open_website")
        self.assertEqual(decision.target, "linkedin")

    def test_open_ended_question_is_left_for_gemini(self) -> None:
        self.assertIsNone(self.router.route("explain quantum computing simply"))

    def test_routes_name_question_with_punctuation_locally(self) -> None:
        decision = self.router.route("What's my name?")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "recall")
        self.assertEqual(decision.target, "name")

    def test_routes_saved_favorite_song_request(self) -> None:
        decision = self.router.route("play my favorite song")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "play_favorite_song")

    def test_routes_natural_favorite_song_memory_variations_locally(self) -> None:
        commands = (
            "Remember my favourite song is Skyfall.",
            "Remember that my favorite song is Skyfall",
            "Save Skyfall as my favorite song",
            "My favorite song is Skyfall",
        )
        for command in commands:
            with self.subTest(command=command):
                decision = self.router.route(command)
                self.assertIsNotNone(decision)
                self.assertEqual(decision.action, "remember")
                self.assertEqual(decision.target, "favorite_song")
                self.assertEqual(decision.value, "skyfall")

    def test_incomplete_favorite_song_memory_command_does_not_use_gemini(self) -> None:
        decision = self.router.route("remember my favorite song is")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "unsupported")
        self.assertIn("Tell me the song name", decision.spoken_response)

    def test_routes_bare_known_song_title(self) -> None:
        decision = self.router.route("Skyfall")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "play_song")
        self.assertEqual(decision.target, "skyfall")

    def test_routes_media_and_back_commands(self) -> None:
        self.assertEqual(self.router.route("ruk jao").action, "media_pause")
        self.assertEqual(self.router.route("play").action, "media_play")
        self.assertEqual(self.router.route("go back").action, "close_window")
        self.assertEqual(
            self.router.route("previous page").action,
            "navigate_back",
        )

    def test_routes_news_variations_locally(self) -> None:
        for command in ("today's news", "latest headlines", "aaj ki khabar"):
            with self.subTest(command=command):
                self.assertEqual(self.router.route(command).action, "get_news")

    def test_routes_time_and_date_locally(self) -> None:
        self.assertEqual(self.router.route("what time is it?").action, "get_time")
        self.assertEqual(
            self.router.route("what is today's date?").action,
            "get_date",
        )

    def test_routes_weather_with_optional_city_locally(self) -> None:
        decision = self.router.route("what is the weather in Goa?")
        self.assertEqual(decision.action, "get_weather")
        self.assertEqual(decision.target, "goa")

        default_city = self.router.route("tell me the weather")
        self.assertEqual(default_city.action, "get_weather")
        self.assertIsNone(default_city.target)

        rain = self.router.route("will it rain in Delhi today?")
        self.assertEqual(rain.action, "get_weather")
        self.assertEqual(rain.target, "delhi")

        hinglish = self.router.route("Goa ka mausam kaisa hai?")
        self.assertEqual(hinglish.action, "get_weather")
        self.assertEqual(hinglish.target, "goa")

        default_hinglish = self.router.route("aaj ka mausam kaisa hai?")
        self.assertEqual(default_hinglish.action, "get_weather")
        self.assertIsNone(default_hinglish.target)


class GeminiRouterTests(unittest.TestCase):
    def test_parses_structured_gemini_decision(self) -> None:
        router = GeminiRouter()
        fake_client = FakeGeminiClient()
        router._client = fake_client

        decision = router.route(
            "could you take me to LinkedIn please",
            allowed_sites={"linkedin", "youtube"},
            known_songs={"skyfall"},
        )

        self.assertEqual(decision.action, "open_website")
        self.assertEqual(decision.target, "linkedin")
        self.assertEqual(fake_client.interactions.last_request["model"], router.model)
        self.assertEqual(
            fake_client.interactions.last_request["timeout"],
            min(router.timeout_seconds, 5.0),
        )
        self.assertEqual(
            fake_client.interactions.last_request["response_format"]["mime_type"],
            "application/json",
        )

    def test_enforces_application_level_timeout(self) -> None:
        router = GeminiRouter()
        router._client = SlowGeminiClient()
        router.timeout_seconds = 0.01

        start = time.perf_counter()
        with self.assertRaisesRegex(Exception, "did not respond"):
            router.route(
                "take me somewhere",
                allowed_sites={"linkedin"},
                known_songs=set(),
            )

        self.assertLess(time.perf_counter() - start, 0.15)


class ActionExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        memory = MemoryStore(Path(self.temp_dir.name) / "memory.json")
        self.executor = ActionExecutor(memory, dry_run=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rejects_unapproved_website(self) -> None:
        result = self.executor.execute(
            CommandDecision(action="open_website", target="unknown")
        )
        self.assertIn("approved list", result)

    def test_remembers_and_recalls_value(self) -> None:
        self.executor.execute(
            CommandDecision(
                action="remember",
                target="name",
                value="Bablu",
                spoken_response="Saved.",
            )
        )
        result = self.executor.execute(CommandDecision(action="recall", target="name"))
        self.assertIn("Bablu", result)

    def test_plays_the_song_saved_in_memory(self) -> None:
        self.executor.memory.save("favorite_song", "Skyfall")
        with patch.object(self.executor, "_open") as mock_open:
            result = self.executor.execute(
                CommandDecision(action="play_favorite_song")
            )

        self.assertEqual(result, "Playing skyfall.")
        mock_open.assert_called_once_with("https://youtu.be/DeumyOzKqgI")

    def test_media_and_back_actions_use_the_system_controller(self) -> None:
        controller = Mock()
        controller.toggle_playback.return_value = True
        controller.go_back.return_value = True
        controller.close_window.return_value = True
        executor = ActionExecutor(
            self.executor.memory,
            dry_run=True,
            system_controller=controller,
        )

        self.assertEqual(
            executor.execute(CommandDecision(action="media_pause")),
            "Pausing playback.",
        )
        self.assertEqual(
            executor.execute(CommandDecision(action="media_play")),
            "Resuming playback.",
        )
        self.assertEqual(
            executor.execute(CommandDecision(action="navigate_back")),
            "Going back.",
        )
        self.assertEqual(
            executor.execute(CommandDecision(action="close_window")),
            "Closing the current window.",
        )
        self.assertEqual(controller.toggle_playback.call_count, 2)
        controller.go_back.assert_called_once_with()
        controller.close_window.assert_called_once_with()

    def test_news_dry_run_does_not_call_network(self) -> None:
        result = self.executor.execute(CommandDecision(action="get_news"))
        self.assertIn("Dry run", result)

    def test_time_and_date_are_available_without_network(self) -> None:
        time_result = self.executor.execute(CommandDecision(action="get_time"))
        date_result = self.executor.execute(CommandDecision(action="get_date"))

        self.assertRegex(time_result, r"The current time is \d{1,2}:\d{2} [AP]M\.")
        self.assertTrue(date_result.startswith("Today is "))

    def test_weather_uses_requested_or_default_city(self) -> None:
        weather_service = Mock()
        weather_service.current_summary.side_effect = lambda city: f"Weather: {city}"
        with patch.dict("os.environ", {"DEFAULT_CITY": "Pune"}):
            executor = ActionExecutor(
                self.executor.memory,
                dry_run=False,
                weather_service=weather_service,
            )

        requested = executor.execute(
            CommandDecision(action="get_weather", target="Mumbai")
        )
        defaulted = executor.execute(CommandDecision(action="get_weather"))

        self.assertEqual(requested, "Weather: Mumbai")
        self.assertEqual(defaulted, "Weather: Pune")
        self.assertEqual(
            weather_service.current_summary.call_args_list,
            [call("Mumbai"), call("Pune")],
        )

    @patch.dict("os.environ", {"NEWS_API_KEY": "test-key"})
    @patch("jarvis_ai.actions.requests.get")
    def test_news_reports_invalid_key(self, mock_get: Mock) -> None:
        response = Mock()
        response.status_code = 401
        response.json.return_value = {"status": "error", "code": "apiKeyInvalid"}
        mock_get.return_value = response
        live_executor = ActionExecutor(self.executor.memory, dry_run=False)

        result = live_executor.execute(CommandDecision(action="get_news"))

        self.assertIn("rejected the API key", result)

    @patch.dict("os.environ", {"NEWS_API_KEY": "test-key"})
    @patch("jarvis_ai.actions.requests.get")
    def test_news_uses_latest_india_query(self, mock_get: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "status": "ok",
            "articles": [
                {"title": "First headline"},
                {"title": "Second headline"},
                {"title": "Third headline"},
            ],
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response
        live_executor = ActionExecutor(self.executor.memory, dry_run=False)

        result = live_executor.execute(CommandDecision(action="get_news"))

        self.assertIn("First headline", result)
        request_url = mock_get.call_args.args[0]
        request_params = mock_get.call_args.kwargs["params"]
        self.assertTrue(request_url.endswith("/everything"))
        self.assertEqual(request_params["q"], "India")
        self.assertEqual(request_params["sortBy"], "publishedAt")


class SpeakerTests(unittest.TestCase):
    @patch("jarvis_ai.speech.pygame")
    @patch("jarvis_ai.speech.gTTS")
    def test_uses_gtts_and_pygame_for_primary_voice(
        self,
        mock_gtts: Mock,
        mock_pygame: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_pygame.mixer.get_init.return_value = True
            mock_pygame.mixer.music.get_busy.return_value = False
            mock_gtts.return_value.save.side_effect = (
                lambda path: Path(path).write_bytes(b"fake mp3 data")
            )
            speaker = Speaker(cache_dir=Path(temp_dir))

            speaker.say("Opening YouTube")

            mock_gtts.assert_called_once_with(
                text="Opening YouTube",
                lang="en",
                timeout=5,
            )
            mock_gtts.return_value.save.assert_called_once()
            mock_pygame.mixer.music.play.assert_called_once()

    @patch("jarvis_ai.speech.pygame")
    @patch("jarvis_ai.speech.gTTS")
    def test_reuses_cached_voice_without_second_generation(
        self,
        mock_gtts: Mock,
        mock_pygame: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_pygame.mixer.get_init.return_value = True
            mock_pygame.mixer.music.get_busy.return_value = False
            mock_gtts.return_value.save.side_effect = (
                lambda path: Path(path).write_bytes(b"fake mp3 data")
            )
            speaker = Speaker(cache_dir=Path(temp_dir))

            speaker.say("Opening YouTube")
            speaker.say("Opening YouTube")

            mock_gtts.assert_called_once()
            self.assertEqual(mock_pygame.mixer.music.play.call_count, 2)

    @patch("jarvis_ai.speech.pygame")
    @patch("jarvis_ai.speech.gTTS", side_effect=RuntimeError("network unavailable"))
    def test_voice_cache_preparation_stops_cleanly_on_network_failure(
        self,
        _mock_gtts: Mock,
        mock_pygame: Mock,
    ) -> None:
        mock_pygame.mixer.get_init.return_value = True
        with tempfile.TemporaryDirectory() as temp_dir:
            result = Speaker(cache_dir=Path(temp_dir)).prepare(["One", "Two"])

        self.assertEqual(result, (0, 0, 2))

    @patch("jarvis_ai.speech.pyttsx3.init")
    @patch("jarvis_ai.speech.gTTS", side_effect=RuntimeError("offline"))
    def test_falls_back_to_windows_voice(
        self,
        _mock_gtts: Mock,
        mock_pyttsx3_init: Mock,
    ) -> None:
        engine = mock_pyttsx3_init.return_value

        with tempfile.TemporaryDirectory() as temp_dir:
            Speaker(cache_dir=Path(temp_dir)).say("Yes boss, I'm listening.")

        engine.say.assert_called_once_with("Yes boss, I'm listening.")
        engine.runAndWait.assert_called_once()


class WindowsMediaControllerTests(unittest.TestCase):
    def test_close_window_sends_alt_f4_without_touching_the_real_window(self) -> None:
        controller = WindowsMediaController()
        with patch.object(controller, "_key") as mock_key:
            result = controller.close_window()

        self.assertTrue(result)
        self.assertEqual(
            mock_key.call_args_list,
            [
                call(controller.VK_MENU),
                call(controller.VK_F4),
                call(controller.VK_F4, key_up=True),
                call(controller.VK_MENU, key_up=True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
