"""Local Flask dashboard for the Jarvis AI Assistant."""

from __future__ import annotations

import argparse
import secrets
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from jarvis_ai.assistant import JarvisAssistant
from jarvis_ai.dashboard_voice import DashboardVoiceSession


ROOT = Path(__file__).resolve().parent


def create_app(
    *,
    data_dir: Path | None = None,
    dry_run: bool = False,
    assistant: JarvisAssistant | None = None,
    voice_session: DashboardVoiceSession | None = None,
) -> Flask:
    app = Flask(__name__)
    # This is a local development dashboard. Never let the browser keep an old
    # microphone script after the user restarts Jarvis during development.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    jarvis = assistant or JarvisAssistant(
        data_dir=data_dir or ROOT,
        dry_run=dry_run,
    )
    dashboard_voice = voice_session or DashboardVoiceSession(
        transcript_selector=jarvis.select_voice_transcript,
    )
    pending_start_day_tokens: set[str] = set()
    start_day_token_lock = threading.Lock()

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.path == "/" or request.path.startswith(("/api/", "/static/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ready",
                "ai_available": jarvis.ai_available,
                "default_city": jarvis.executor.default_city,
                "desktop_voice_available": dashboard_voice.available,
                "voice": dashboard_voice.status(),
            }
        )

    @app.post("/api/voice/start")
    def start_voice():
        try:
            return jsonify(dashboard_voice.start())
        except RuntimeError as error:
            return jsonify({"error": str(error)}), 503

    @app.post("/api/voice/stop")
    def stop_voice():
        return jsonify(dashboard_voice.stop())

    @app.post("/api/voice/pause")
    def pause_voice():
        return jsonify(dashboard_voice.pause())

    @app.post("/api/voice/resume")
    def resume_voice():
        return jsonify(dashboard_voice.resume())

    @app.post("/api/voice/standby")
    def standby_voice():
        state = dashboard_voice.standby()
        if not state["enabled"]:
            return jsonify({"error": "Voice mode is not running."}), 409
        return jsonify(state)

    @app.get("/api/voice/events")
    def voice_events():
        try:
            after = max(0, int(request.args.get("after", "0")))
        except ValueError:
            return jsonify({"error": "Invalid event cursor."}), 400
        return jsonify(
            {
                "events": dashboard_voice.events_after(after),
                **dashboard_voice.status(),
            }
        )

    @app.post("/api/command")
    def command():
        payload = request.get_json(silent=True) or {}
        command_text = str(payload.get("command", "")).strip()
        if not command_text:
            return jsonify({"error": "Please enter a command."}), 400
        if len(command_text) > 500:
            return jsonify({"error": "Command is too long."}), 400

        try:
            result = jarvis.handle(
                command_text,
                defer_start_day_actions=True,
            )
        except Exception:
            app.logger.exception("Jarvis command failed")
            return jsonify(
                {"error": "Jarvis could not complete that command."}
            ), 500
        response = result.model_dump()
        if result.action == "start_my_day":
            token = secrets.token_urlsafe(24)
            with start_day_token_lock:
                # This is a single-user local dashboard. Keep only a small
                # number of pending routines so abandoned tabs cannot grow
                # the in-memory token set indefinitely.
                if len(pending_start_day_tokens) >= 20:
                    pending_start_day_tokens.clear()
                pending_start_day_tokens.add(token)
            response["follow_up"] = {
                "action": "complete_start_my_day",
                "token": token,
            }
        else:
            response["follow_up"] = None
        return jsonify(response)

    @app.post("/api/start-day/complete")
    def complete_start_day():
        payload = request.get_json(silent=True) or {}
        token = str(payload.get("token", "")).strip()
        with start_day_token_lock:
            if not token or token not in pending_start_day_tokens:
                return jsonify(
                    {"error": "This morning routine is no longer pending."}
                ), 409
            pending_start_day_tokens.remove(token)

        try:
            message = jarvis.complete_start_my_day()
        except Exception:
            app.logger.exception("Jarvis morning actions failed")
            return jsonify(
                {"error": "Jarvis could not finish the morning setup."}
            ), 500
        return jsonify({"message": message})

    @app.get("/api/reminders")
    def list_reminders():
        return jsonify({"reminders": jarvis.list_reminders()})

    @app.post("/api/reminders")
    def add_reminder():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return jsonify({"error": "Reminder cannot be empty."}), 400
        try:
            saved = jarvis.add_reminder(text)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(
            {"message": f"Reminder saved: {saved}.", "reminder": saved}
        ), 201

    @app.delete("/api/reminders/<int:index>")
    def remove_reminder(index: int):
        try:
            removed = jarvis.remove_reminder(index)
        except IndexError:
            return jsonify({"error": "Reminder does not exist."}), 404
        return jsonify({"message": f"Removed reminder: {removed}."})

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Jarvis dashboard.")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the dashboard automatically.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without opening websites or calling NewsAPI.",
    )
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    app = create_app(dry_run=args.dry_run)
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Jarvis dashboard is ready at {url}")
    app.run(
        host="127.0.0.1",
        port=args.port,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
