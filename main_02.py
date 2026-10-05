"""Canonical entry point for the Jarvis AI Assistant."""

from __future__ import annotations

import argparse
from pathlib import Path

import speech_recognition as sr
from dotenv import load_dotenv

import music_library

from jarvis_ai.assistant import JarvisAssistant
from jarvis_ai.speech import Speaker


WAKE_WORDS = (
    "jarvis",
    "hey jarvis",
    "hello jarvis",
    "ok jarvis",
    "wake up jarvis",
)

ACTIVATION_RESPONSE = "Yes boss, I'm listening."

DEMO_VOICE_LINES = (
    "Jarvis is ready.",
    ACTIVATION_RESPONSE,
    "Opening YouTube.",
    "Opening Google.",
    "Opening Instagram.",
    "Opening LinkedIn.",
    "Opening Facebook.",
    "Opening GitHub.",
    "Opening WhatsApp.",
    "Opening Telegram",
    "Going to sleep mode.",
    "Goodbye.",
    "Voice output is working. I am ready, boss.",
    "Pausing playback.",
    "Resuming playback.",
    "Going back.",
    "Closing the current browser tab.",
    "Closing the current window.",
    *(f"Playing {song}." for song in music_library.music),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A safe, Gemini-powered voice and text assistant."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--text",
        action="store_true",
        help="Run an interactive text chat instead of using the microphone.",
    )
    mode.add_argument(
        "--command",
        metavar="TEXT",
        help="Process one command and exit.",
    )
    mode.add_argument(
        "--voice-test",
        action="store_true",
        help="Speak one test sentence and exit.",
    )
    mode.add_argument(
        "--prepare-voice-cache",
        action="store_true",
        help="Pre-generate common spoken responses for low-latency demos.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Describe actions without opening websites or calling NewsAPI.",
    )
    parser.add_argument(
        "--mute",
        action="store_true",
        help="Print responses without speaking them aloud.",
    )
    return parser


def respond(assistant: JarvisAssistant, speaker: Speaker, command: str) -> None:
    result = assistant.handle(command)
    print(f"Jarvis [{result.source}]: {result.message}")
    speaker.say(result.message)


def run_text_mode(assistant: JarvisAssistant, speaker: Speaker) -> None:
    print("Jarvis text mode is ready. Type 'exit' to stop.")
    while True:
        try:
            command = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not command:
            continue
        if command.lower() in {"exit", "quit", "shutdown"}:
            break
        respond(assistant, speaker, command)


def listen(
    recognizer: sr.Recognizer,
    *,
    timeout: int,
    phrase_time_limit: int,
) -> str:
    with sr.Microphone() as source:
        audio = recognizer.listen(
            source,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )
    return recognizer.recognize_google(audio, language="en-IN").strip()


def run_voice_mode(assistant: JarvisAssistant, speaker: Speaker) -> None:
    recognizer = sr.Recognizer()
    print("Calibrating microphone for background noise...")
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)

    # Allow natural pauses inside a command. The previous 0.55-second threshold
    # was too aggressive and could cut off a speaker before the sentence ended.
    recognizer.pause_threshold = 1.35
    recognizer.non_speaking_duration = 0.65
    recognizer.phrase_threshold = 0.25
    recognizer.operation_timeout = 12

    print("Jarvis is ready. Say 'Jarvis' to activate it.")
    speaker.say("Jarvis is ready.")
    active = False

    while True:
        try:
            if not active:
                print("Listening for wake word...")
                heard = listen(recognizer, timeout=5, phrase_time_limit=4)
                print(f"Heard: {heard}")
                if any(wake_word in heard.lower() for wake_word in WAKE_WORDS):
                    active = True
                    print(f"Jarvis: {ACTIVATION_RESPONSE}")
                    speaker.say(ACTIVATION_RESPONSE)
                continue

            print("Listening for command...")
            command = listen(recognizer, timeout=7, phrase_time_limit=15)
            print(f"Command: {command}")

            if command.lower() == "sleep":
                active = False
                speaker.say("Going to sleep mode.")
            elif command.lower() in {"exit", "quit", "shutdown"}:
                speaker.say("Goodbye.")
                break
            else:
                respond(assistant, speaker, command)

        except sr.WaitTimeoutError:
            print("No speech detected.")
        except sr.UnknownValueError:
            print("I could not understand the audio.")
        except sr.RequestError as error:
            print(f"Speech recognition is unavailable: {error}")
        except KeyboardInterrupt:
            print("\nJarvis stopped.")
            break


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    speaker = Speaker(enabled=not args.mute)

    if args.prepare_voice_cache:
        generated, cached, failed = speaker.prepare(DEMO_VOICE_LINES)
        print(
            "Voice cache result: "
            f"{generated} generated, {cached} already cached, {failed} not cached."
        )
        return

    if args.voice_test:
        message = "Voice output is working. I am ready, boss."
        print(f"Jarvis: {message}")
        speaker.say(message)
        return

    # Keep preferences in the project's original memory.json. This is the same
    # file used by the earlier version of Jarvis, so saved names and songs are
    # not split between two different memory locations.
    project_dir = Path(__file__).resolve().parent
    assistant = JarvisAssistant(data_dir=project_dir, dry_run=args.dry_run)

    if not assistant.ai_available:
        print(
            "Gemini is not configured. Built-in commands still work; "
            "add GEMINI_API_KEY to .env to enable natural-language routing."
        )

    if args.command:
        respond(assistant, speaker, args.command)
    elif args.text:
        run_text_mode(assistant, speaker)
    else:
        run_voice_mode(assistant, speaker)


if __name__ == "__main__":
    main()
