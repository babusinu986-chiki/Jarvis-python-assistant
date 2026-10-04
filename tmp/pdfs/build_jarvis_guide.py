from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "jarvis_ai_assistant_guide.pdf"

NAVY = colors.HexColor("#0B1830")
NAVY_2 = colors.HexColor("#142748")
TEAL = colors.HexColor("#20C7B5")
CYAN = colors.HexColor("#57D4FF")
AMBER = colors.HexColor("#F2B84B")
INK = colors.HexColor("#162033")
MUTED = colors.HexColor("#5F6B7A")
LIGHT = colors.HexColor("#F3F7FA")
LINE = colors.HexColor("#D7E0E8")
WHITE = colors.white


def register_fonts() -> tuple[str, str]:
    regular = Path("C:/Windows/Fonts/segoeui.ttf")
    bold = Path("C:/Windows/Fonts/segoeuib.ttf")
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("Segoe", str(regular)))
        pdfmetrics.registerFont(TTFont("Segoe-Bold", str(bold)))
        return "Segoe", "Segoe-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = register_fonts()
styles = getSampleStyleSheet()

TITLE = ParagraphStyle(
    "Title",
    parent=styles["Title"],
    fontName=FONT_BOLD,
    fontSize=29,
    leading=34,
    textColor=WHITE,
    alignment=TA_LEFT,
    spaceAfter=10,
)
SUBTITLE = ParagraphStyle(
    "Subtitle",
    parent=styles["BodyText"],
    fontName=FONT,
    fontSize=13,
    leading=19,
    textColor=colors.HexColor("#D9E6F2"),
)
H1 = ParagraphStyle(
    "H1",
    parent=styles["Heading1"],
    fontName=FONT_BOLD,
    fontSize=20,
    leading=24,
    textColor=NAVY,
    spaceBefore=2,
    spaceAfter=10,
)
H1_COMPACT = ParagraphStyle(
    "H1Compact",
    parent=H1,
    fontSize=18,
    leading=21,
    spaceAfter=8,
)
H2 = ParagraphStyle(
    "H2",
    parent=styles["Heading2"],
    fontName=FONT_BOLD,
    fontSize=12.5,
    leading=16,
    textColor=NAVY_2,
    spaceBefore=8,
    spaceAfter=5,
)
BODY = ParagraphStyle(
    "Body",
    parent=styles["BodyText"],
    fontName=FONT,
    fontSize=9.4,
    leading=13.2,
    textColor=INK,
    spaceAfter=5,
)
SMALL = ParagraphStyle(
    "Small",
    parent=BODY,
    fontSize=8.2,
    leading=11,
    textColor=MUTED,
)
CALLOUT = ParagraphStyle(
    "Callout",
    parent=BODY,
    fontName=FONT_BOLD,
    fontSize=10.2,
    leading=14,
    textColor=NAVY,
)
TABLE_HEAD = ParagraphStyle(
    "TableHead",
    parent=BODY,
    fontName=FONT_BOLD,
    fontSize=8.3,
    leading=10.5,
    textColor=WHITE,
    alignment=TA_LEFT,
)
TABLE_BODY = ParagraphStyle(
    "TableBody",
    parent=BODY,
    fontSize=8.1,
    leading=10.6,
    spaceAfter=0,
)
TABLE_BODY_BOLD = ParagraphStyle(
    "TableBodyBold",
    parent=TABLE_BODY,
    fontName=FONT_BOLD,
    textColor=NAVY,
)
CODE = ParagraphStyle(
    "Code",
    parent=BODY,
    fontName="Courier",
    fontSize=8.3,
    leading=11,
    textColor=colors.HexColor("#E8F2FF"),
    backColor=NAVY,
    borderPadding=8,
    spaceBefore=4,
    spaceAfter=8,
)


def P(text: str, style=BODY) -> Paragraph:
    return Paragraph(text, style)


def bullet(text: str) -> Paragraph:
    return Paragraph(f"- {text}", BODY)


def compact_bullet(text: str) -> Paragraph:
    style = ParagraphStyle(
        "CompactBullet",
        parent=SMALL,
        fontSize=8.3,
        leading=10.4,
        textColor=INK,
        spaceAfter=1.5,
    )
    return Paragraph(f"- {text}", style)


def section_label(text: str) -> Table:
    table = Table([[P(text.upper(), TABLE_HEAD)]], colWidths=[44 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), TEAL),
                ("BOX", (0, 0), (-1, -1), 0, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def callout(title: str, body: str, accent=TEAL) -> Table:
    content = P(f"<b>{title}</b><br/>{body}", BODY)
    table = Table([["", content]], colWidths=[4 * mm, 164 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def data_table(rows, widths, header=True) -> Table:
    cooked = []
    for row_index, row in enumerate(rows):
        style = TABLE_HEAD if header and row_index == 0 else TABLE_BODY
        cooked.append([P(str(cell), style) for cell in row])
    table = Table(cooked, colWidths=widths, repeatRows=1 if header else 0)
    style_commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style_commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY_2))
        for row_index in range(1, len(rows)):
            if row_index % 2 == 0:
                style_commands.append(
                    ("BACKGROUND", (0, row_index), (-1, row_index), LIGHT)
                )
    table.setStyle(TableStyle(style_commands))
    return table


def flow_row(labels, colors_list) -> Table:
    cells = []
    for index, label in enumerate(labels):
        cells.append(P(label, ParagraphStyle(
            f"flow-{index}",
            parent=TABLE_BODY,
            fontName=FONT_BOLD,
            fontSize=8.1,
            leading=10.5,
            alignment=TA_CENTER,
            textColor=WHITE,
        )))
        if index < len(labels) - 1:
            cells.append(P(">", ParagraphStyle(
                f"arrow-{index}",
                parent=TABLE_BODY,
                fontName=FONT_BOLD,
                fontSize=12,
                alignment=TA_CENTER,
                textColor=NAVY,
            )))
    widths = []
    for index in range(len(cells)):
        widths.append(31 * mm if index % 2 == 0 else 7 * mm)
    table = Table([cells], colWidths=widths)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]
    for index, color in enumerate(colors_list):
        commands.append(("BACKGROUND", (index * 2, 0), (index * 2, 0), color))
        commands.append(("BOX", (index * 2, 0), (index * 2, 0), 0.5, color))
    table.setStyle(TableStyle(commands))
    return table


def draw_cover(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(NAVY_2)
    canvas.circle(width - 42 * mm, height - 24 * mm, 56 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.circle(width - 23 * mm, height - 18 * mm, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, 0, 10 * mm, height, fill=1, stroke=0)
    canvas.restoreState()


def draw_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, height - 16 * mm, width - 20 * mm, height - 16 * mm)
    canvas.setFont(FONT_BOLD, 8)
    canvas.setFillColor(NAVY)
    canvas.drawString(20 * mm, height - 12 * mm, "JARVIS AI ASSISTANT")
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - 20 * mm, 12 * mm, f"Page {doc.page}")
    canvas.drawString(20 * mm, 12 * mm, "Command and capability guide")
    canvas.restoreState()


def build_story():
    story = []

    story += [
        Spacer(1, 34 * mm),
        section_label("Portfolio Project Guide"),
        Spacer(1, 10 * mm),
        P("Jarvis AI Assistant", TITLE),
        P(
            "Voice commands, Gemini capabilities, architecture, latency behavior, "
            "demo flow, limitations, and troubleshooting.",
            SUBTITLE,
        ),
        Spacer(1, 18 * mm),
        Table(
            [
                [P("VOICE", TABLE_HEAD), P("RULES", TABLE_HEAD), P("GEMINI", TABLE_HEAD)],
                [
                    P("Wake-word control and spoken replies", SUBTITLE),
                    P("Fast, deterministic local actions", SUBTITLE),
                    P("Flexible language understanding", SUBTITLE),
                ],
            ],
            colWidths=[55 * mm, 55 * mm, 55 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                    ("BACKGROUND", (0, 1), (-1, 1), NAVY_2),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#426184")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#426184")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
        Spacer(1, 30 * mm),
        P("Prepared for project demonstration and Hacker House Goa application", SUBTITLE),
        P("Version reviewed on 4 October 2026", SUBTITLE),
        PageBreak(),
    ]

    story += [
        P("1. Current Project at a Glance", H1),
        P(
            "Jarvis is a Python voice and text assistant. It listens for a wake word, "
            "recognizes a command, selects either a fast local rule or Gemini routing, "
            "validates the resulting action, performs an approved operation, and replies aloud.",
            BODY,
        ),
        Spacer(1, 3 * mm),
        callout(
            "Verified status",
            "13 automated tests pass. Microphone initialization succeeds. Common voice "
            "responses are cached. Flexible website phrases can be handled locally. Gemini "
            "has a five-second application deadline so a weak network cannot freeze the demo.",
        ),
        Spacer(1, 6 * mm),
        P("Execution pipeline", H2),
        flow_row(
            ["Voice or text", "Local rule", "Gemini fallback", "Safety check", "Action + reply"],
            [NAVY_2, TEAL, colors.HexColor("#5A67D8"), AMBER, colors.HexColor("#247A67")],
        ),
        Spacer(1, 7 * mm),
        P("How to start Jarvis", H2),
        P("Voice mode", TABLE_BODY_BOLD),
        P("python main_02.py", CODE),
        Spacer(1, 2 * mm),
        P("Text mode for debugging", TABLE_BODY_BOLD),
        P("python main_02.py --text --mute", CODE),
        Spacer(1, 2 * mm),
        P("Safe one-command test", TABLE_BODY_BOLD),
        P('python main_02.py --command "open youtube" --dry-run --mute', CODE),
        callout(
            "Voice timing settings",
            "Jarvis now allows 1.10 seconds of silence inside a sentence, records a command "
            "for up to 15 seconds, and limits speech-recognition network operations to 8 seconds. "
            "This prevents premature cutoff while keeping failure recovery bounded.",
            CYAN,
        ),
        PageBreak(),
    ]

    command_rows = [
        ["Category", "Say or type", "What Jarvis does"],
        ["Activate", "Jarvis / Hey Jarvis / Hello Jarvis / OK Jarvis / Wake up Jarvis", "Enters active command mode and says: Yes boss, I'm listening."],
        ["Open website", "Open YouTube / Google / Instagram / LinkedIn / Facebook / GitHub", "Opens the approved website in the default browser."],
        ["Flexible website", "Could you take me to LinkedIn? / Launch YouTube", "Routes locally without waiting for Gemini."],
        ["Web search", "Search for Python voice assistants / Look up AI hackathons", "Opens a Google search for the requested topic."],
        ["Music", "Play Skyfall", "Opens the saved link when the title exists in music_library.py."],
        ["News", "News / Tell me the news / Read today's news", "Requests up to three Indian headlines through NewsAPI."],
        ["Save name", "Remember my name is Bablu", "Stores the name in local JSON memory."],
        ["Recall name", "What is my name?", "Reads the saved name aloud."],
        ["Save song", "Remember my favorite song is Skyfall", "Stores the favorite song locally."],
        ["Recall song", "What is my favorite song?", "Reads the stored favorite song."],
        ["Standby", "Sleep", "Returns to wake-word listening mode."],
        ["Exit", "Exit / Quit / Shutdown", "Stops the assistant cleanly."],
    ]
    story += [
        P("2. Local Command Reference", H1),
        P(
            "These commands are handled by deterministic Python rules. They are the fastest "
            "and most dependable choices for a live presentation because they do not wait for Gemini.",
            BODY,
        ),
        data_table(command_rows, [31 * mm, 68 * mm, 69 * mm]),
        Spacer(1, 6 * mm),
        callout(
            "Current music library",
            "Skyfall, Think, This, Idiot, and Bhojpuri. Other titles are rejected until their "
            "links are added to music_library.py.",
            AMBER,
        ),
        PageBreak(),
    ]

    gemini_rows = [
        ["Gemini capability", "Current behavior", "Boundary"],
        ["Intent understanding", "Converts an unmatched natural-language request into validated JSON.", "It can choose only one action from the defined schema."],
        ["Flexible website routing", "Can map conversational wording to an approved site.", "The executor still rejects every site outside the allow-list."],
        ["Search routing", "Can extract a search query and request the web-search action.", "Jarvis opens Google; Gemini does not inspect the result."],
        ["Memory routing", "Can classify remember and recall requests.", "Memory is a small local JSON store, not a private knowledge vault."],
        ["Short conversation", "Can answer harmless general questions in up to two short sentences.", "Answers may be incomplete and are not guaranteed to be current."],
        ["Safe refusal", "Classifies unclear or risky requests as unsupported.", "No arbitrary code, shell, credentials, purchases, or file operations."],
    ]
    story += [
        P("3. Gemini Capabilities - Separate from Local Commands", H1_COMPACT),
        P(
            "Gemini handles requests that local rules do not understand. It proposes a structured "
            "decision; Python validates it before anything happens.",
            BODY,
        ),
        data_table(gemini_rows, [42 * mm, 64 * mm, 62 * mm]),
        Spacer(1, 6 * mm),
        callout(
            "Network behavior",
            "Gemini needs internet access and may be affected by latency, quota, or retries. Jarvis "
            "returns control after five seconds. Demonstrate local commands first, then show one "
            "Gemini question after confirming the connection.",
            colors.HexColor("#5A67D8"),
        ),
        Spacer(1, 5 * mm),
        P("What Gemini currently cannot do", H2),
        compact_bullet("Execute arbitrary Python, PowerShell, terminal, or operating-system commands."),
        compact_bullet("Open unapproved websites or arbitrary desktop applications."),
        compact_bullet("Send WhatsApp messages, emails, social posts, or purchases."),
        compact_bullet("Read, edit, delete, or upload local files."),
        compact_bullet("Guarantee real-time facts unless a dedicated external service is used."),
        PageBreak(),
    ]

    latency_rows = [
        ["Stage", "Typical behavior", "Optimization now in place"],
        ["End-of-speech detection", "Local microphone timing", "1.10-second pause tolerance prevents sentence cutoff."],
        ["Local routing", "Measured at about 0.006 seconds", "Rule-based commands avoid Gemini completely."],
        ["Voice playback", "First unique gTTS line needs network", "Persistent cache; common responses are pre-generated."],
        ["Cached voice lookup", "Measured at about 0.11 milliseconds", "Immediate reuse of the stored MP3."],
        ["Gemini routing", "Variable network delay", "Five-second hard application deadline and local paraphrase rules."],
        ["Speech recognition", "Uses Google's online recognizer", "Eight-second operation timeout prevents indefinite waiting."],
        ["News", "Uses NewsAPI", "Clear errors for invalid keys, quota limits, and network failures."],
    ]
    story += [
        P("4. Performance and Network Dependencies", H1),
        data_table(latency_rows, [43 * mm, 57 * mm, 68 * mm]),
        Spacer(1, 7 * mm),
        P("What is local and what needs the internet", H2),
        data_table(
            [
                ["Component", "Internet?", "Notes"],
                ["Wake-word loop and command rules", "No", "Runs in Python on the computer."],
                ["Speech-to-text", "Yes", "Google Speech Recognition processes recorded audio."],
                ["Cached spoken replies", "No", "Previously generated MP3 audio plays locally."],
                ["New gTTS reply", "Yes", "Generated once, then cached automatically."],
                ["Gemini", "Yes", "Used only when local rules do not match."],
                ["NewsAPI", "Yes", "Requires a valid NEWS_API_KEY and available quota."],
            ],
            [60 * mm, 26 * mm, 82 * mm],
        ),
        Spacer(1, 7 * mm),
        callout(
            "Presentation recommendation",
            "Prepare the voice cache, test the microphone, and demonstrate local actions first. "
            "Keep one Gemini example as an optional network-dependent feature rather than making "
            "the entire demonstration depend on external services.",
        ),
        PageBreak(),
    ]

    demo_rows = [
        ["Step", "Presenter action", "Expected result"],
        ["1", "Run python main_02.py", "Jarvis calibrates the microphone and announces readiness."],
        ["2", "Say: Jarvis", "Jarvis says: Yes boss, I'm listening."],
        ["3", "Say: Could you take me to LinkedIn?", "Local rule opens LinkedIn and replies aloud."],
        ["4", "Say: Search for Hacker House Goa", "Google search opens with the requested query."],
        ["5", "Say: Remember my name is Bablu", "Jarvis confirms that the name is stored."],
        ["6", "Say: What is my name?", "Jarvis recalls the stored name."],
        ["7", "Optional: ask one general question", "Gemini returns a short answer or times out safely."],
        ["8", "Say: Sleep, then Jarvis", "Demonstrates standby and wake-word reactivation."],
    ]
    story += [
        P("5.&nbsp;Presentation Demo Script", H1_COMPACT),
        data_table(demo_rows, [15 * mm, 75 * mm, 78 * mm]),
        Spacer(1, 7 * mm),
        P("Pre-demo checklist", H2),
        bullet("Use a quiet room and select the correct Windows microphone."),
        bullet("Run: python main_02.py --prepare-voice-cache"),
        bullet("Run: python main_02.py --voice-test"),
        bullet("Confirm that .env contains valid Gemini and NewsAPI keys without showing them."),
        bullet("Close unnecessary apps and test internet connectivity."),
        bullet("Keep text mode ready as a fallback: python main_02.py --text --mute"),
        Spacer(1, 6 * mm),
        P("Troubleshooting", H2),
        data_table(
            [
                ["Symptom", "Likely cause", "Action"],
                ["Command ends too early", "Long pause or noisy microphone", "Speak continuously; the threshold is now 1.10 seconds."],
                ["No spoken reply", "Started with --mute or audio device problem", "Run --voice-test without --mute."],
                ["New reply is slow", "Gemini or gTTS network latency", "Use a local command or repeat a cached response."],
                ["Gemini falls back", "No response within five seconds", "Check connection, quota, and API key."],
                ["News fails", "Invalid key, quota, or network", "Replace NEWS_API_KEY and rerun the news command."],
            ],
            [42 * mm, 57 * mm, 69 * mm],
        ),
        PageBreak(),
    ]

    story += [
        P("6. Possible Next Improvements", H1),
        P(
            "These features are not implemented yet. They are sensible next steps, but each should "
            "be added with an explicit allow-list, confirmation rules, tests, and a clear demo use case.",
            BODY,
        ),
        data_table(
            [
                ["Improvement", "Value", "Complexity / caution"],
                ["Open approved desktop apps", "More useful computer control", "Medium; use an allow-list and fixed executable paths."],
                ["YouTube search and playback", "Play arbitrary requested videos", "Low to medium; validate search queries and URLs."],
                ["Weather and timers", "Useful everyday assistant functions", "Low; choose reliable APIs and local scheduling."],
                ["Notes and reminders", "Adds productivity value", "Medium; needs storage, editing, and deletion controls."],
                ["WhatsApp or email", "Business communication automation", "High; requires official APIs, consent, and confirmation."],
                ["Desktop user interface", "Better portfolio presentation", "Medium; add visible transcript, state, and action history."],
                ["Streaming Gemini voice", "More natural conversation", "High; network, quota, interruption, and audio complexity."],
            ],
            [47 * mm, 57 * mm, 64 * mm],
        ),
        Spacer(1, 7 * mm),
        callout(
            "Recommended next step",
            "Build a small desktop interface showing Listening, Thinking, Acting, and Speaking states. "
            "This improves presentation quality without expanding into risky system automation.",
            AMBER,
        ),
        Spacer(1, 8 * mm),
        P("Project links and references", H2),
        P(
            "Repository: https://github.com/babusinu986-chiki/Jarvis-python-assistant<br/>"
            "Gemini API documentation: https://ai.google.dev/gemini-api/docs<br/>"
            "Google AI Studio: https://aistudio.google.com/app/apikey<br/>"
            "NewsAPI documentation: https://newsapi.org/docs",
            SMALL,
        ),
        Spacer(1, 7 * mm),
        P(
            "Security note: API keys belong only in the local .env file. Never include them in "
            "screenshots, repositories, demo videos, PDFs, or chat messages.",
            CALLOUT,
        ),
    ]
    return story


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title="Jarvis AI Assistant - Command and Capability Guide",
        author="Jarvis Python Assistant Project",
        subject="Commands, Gemini capabilities, architecture, performance, and demo guide",
    )
    document.build(build_story(), onFirstPage=draw_cover, onLaterPages=draw_page)
    print(OUTPUT)


if __name__ == "__main__":
    main()
