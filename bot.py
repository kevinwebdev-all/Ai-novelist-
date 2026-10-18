import os
import time
import sqlite3
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

MODEL = "openai/gpt-oss-20b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TG = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
DB = sqlite3.connect("novelist.db", check_same_thread=False)

DB.execute("""
CREATE TABLE IF NOT EXISTS projects (
    chat INTEGER PRIMARY KEY,
    title TEXT,
    bible TEXT,
    outline TEXT,
    next_chapter INTEGER DEFAULT 1
)
""")

DB.execute("""
CREATE TABLE IF NOT EXISTS chapters (
    chat INTEGER,
    number INTEGER,
    text TEXT,
    memory TEXT,
    PRIMARY KEY(chat, number)
)
""")
DB.commit()

SYSTEM = """You are a professional novelist and story architect.
Create original, emotionally intelligent, commercially readable fiction.
Characters must have believable motives, flaws, fears, secrets and contradictions.
Show emotion through actions, dialogue, silence and subtext.
Give every character a distinct voice.
Use tension, uncertainty, consequences and earned twists.
Avoid clichés, filler, repetitive phrasing and robotic prose.
Maintain continuity, timeline, relationships and character knowledge.
Never copy existing books or promise sales."""


def ai(prompt, tokens=2200):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing in Railway Variables")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.75,
        "max_completion_tokens": tokens,
        "reasoning_effort": "low",
        "include_reasoning": False
    }

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=180
    )

    if not response.ok:
        detail = response.text[:1000]
        if response.status_code == 413:
            raise RuntimeError(
                "Groq rejected an oversized request. "
                "Reduce the prompt or its output limit."
            )
        raise RuntimeError(
            f"Groq HTTP {response.status_code}: {detail}"
        )

    data = response.json()
    choices = data.get("choices", [])

    if not choices:
        raise RuntimeError("Groq returned no choices.")

    content = choices[0].get("message", {}).get("content", "")

    if not content.strip():
        raise RuntimeError("Groq returned an empty response.")

    return content.strip()


def send(chat, text):
    text = str(text)

    # Telegram messages must remain within its message-length limit.
    for start in range(0, len(text), 3500):
        response = requests.post(
            TG + "/sendMessage",
            json={
                "chat_id": chat,
                "text": text[start:start + 3500]
            },
            timeout=30
        )
        response.raise_for_status()


def project(chat):
    return DB.execute(
        """
        SELECT title, bible, outline, next_chapter
        FROM projects WHERE chat=?
        """,
        (chat,)
    ).fetchone()


def new_story(chat):
    send(chat, "Creating your original novel. Please wait...")

    prompt = """Invent three original novel concepts internally.
Choose the strongest and create its story bible and four-part outline.

Include:
- An original title and genre
- A compelling premise and central conflict
- Main characters, motives, fears, flaws and secrets
- Setting, relationships and timeline
- Major twists and a satisfying planned ending
- Continuity rules to prevent contradictions
- A detailed four-part plot outline

Keep the result focused and useful for writing a full novel.

Use exactly this format:

TITLE: [title]
BIBLE:
[story bible]
OUTLINE:
[outline]"""

    result = ai(prompt, 1800)

    title = "Untitled Novel"
    bible_lines = []
    outline_lines = []
    section = ""

    for line in result.splitlines():
        if line.strip().upper().startswith("TITLE:"):
            title = line.split(":", 1)[1].strip() or title
        elif line.strip().upper() == "BIBLE:":
            section = "bible"
        elif line.strip().upper() == "OUTLINE:":
            section = "outline"
        elif section == "bible":
            bible_lines.append(line)
        elif section == "outline":
            outline_lines.append(line)

    bible = "\n".join(bible_lines).strip() or result
    outline = "\n".join(outline_lines).strip()

    DB.execute(
        """
        INSERT OR REPLACE INTO projects
        (chat, title, bible, outline, next_chapter)
        VALUES (?, ?, ?, ?, 1)
        """,
        (chat, title, bible, outline)
    )

    DB.execute("DELETE FROM chapters WHERE chat=?", (chat,))
    DB.commit()

    send(
        chat,
        f"YOUR NEW NOVEL\n\n{title}\n\n"
        f"STORY BIBLE\n{bible}\n\n"
        f"MASTER OUTLINE\n{outline}\n\n"
        "Send /write to write Chapter 1."
    )


def write_chapter(chat):
    current = project(chat)

    if not current:
        send(chat, "Send /new first. I'll invent the story for you.")
        return

    title, bible, outline, number = current

    recent = DB.execute(
        """
        SELECT number, text, memory
        FROM chapters
        WHERE chat=?
        ORDER BY number DESC
        LIMIT 3
        """,
        (chat,)
    ).fetchall()

    # Keep only compact notes from earlier chapters.
    history = "\n\n".join(
        f"Chapter {chapter_number}: {(memory or '')[:350]}"
        for chapter_number, chapter_text, memory in reversed(recent)
    )

    latest_excerpt = ""
    if recent:
        latest_excerpt = (recent[0][1] or "")[-500:]

    # Strict limits reduce oversized API requests.
    bible = (bible or "")[:1200]
    outline = (outline or "")[:800]
    history = history[:1100]
    latest_excerpt = latest_excerpt[:500]

    send(chat, f"Writing Chapter {number} of {title}...")

    prompt = f"""NOVEL: {title}
CHAPTER NUMBER: {number}

STORY BIBLE:
{bible}

MASTER OUTLINE:
{outline}

PREVIOUS CHAPTER CONTINUITY NOTES:
{history or "This is the opening chapter. Establish the characters and conflict."}

LATEST CHAPTER EXCERPT:
{latest_excerpt}

WRITING REQUIREMENTS:
Write an immersive, polished chapter of approximately 700-900 words.
Continue naturally from the existing story.
Advance the plot without resolving the whole novel.
Maintain character personalities, relationships, timeline and established facts.
Use natural dialogue, emotional depth, tension and meaningful consequences.
Avoid repetitive descriptions, unnecessary summaries and clichés.
End at a compelling point that encourages the reader to continue.

After the chapter, add this exact separator:
[CONTINUITY MEMORY]

After the separator, write concise factual notes about:
- Events that happened
- Character and relationship changes
- Important new facts
- Unresolved questions
- What the next chapter should continue

The continuity notes are not part of the novel chapter."""

    result = ai(prompt, 2200)

    parts = result.split("[CONTINUITY MEMORY]", 1)
    chapter = parts[0].strip()

    if not chapter:
        raise RuntimeError("The AI returned an empty chapter.")

    if len(parts) > 1:
        memory = parts[1].strip()[:1500]
    else:
        memory = (
            "Review the previous chapter before continuing. "
            + chapter[-500:]
        )

    DB.execute(
        """
        INSERT OR REPLACE INTO chapters
        (chat, number, text, memory)
        VALUES (?, ?, ?, ?)
        """,
        (chat, number, chapter, memory)
    )

    DB.execute(
        "UPDATE projects SET next_chapter=? WHERE chat=?",
        (number + 1, chat)
    )

    DB.commit()

    send(chat, f"{title}\nCHAPTER {number}\n\n{chapter}")


def export_pdf(chat):
    current = project(chat)

    if not current:
        send(chat, "No active novel. Send /new first.")
        return

    title, bible, outline, _ = current

    chapters = DB.execute(
        """
        SELECT number, text FROM chapters
        WHERE chat=? ORDER BY number
        """,
        (chat,)
    ).fetchall()

    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak
    )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    content = [
        Paragraph(escape(title), styles["Title"]),
        Spacer(1, 20),
        Paragraph("STORY BIBLE", styles["Heading1"])
    ]

    for line in (bible or "").splitlines():
        if line.strip():
            content.append(
                Paragraph(escape(line), styles["BodyText"])
            )
            content.append(Spacer(1, 5))

    if outline:
        content.append(
            Paragraph("MASTER OUTLINE", styles["Heading1"])
        )

        for line in outline.splitlines():
            if line.strip():
                content.append(
                    Paragraph(escape(line), styles["BodyText"])
                )
                content.append(Spacer(1, 4))

    for number, chapter in chapters:
        content.extend([
            PageBreak(),
            Paragraph(f"Chapter {number}", styles["Heading1"])
        ])

        for paragraph in chapter.splitlines():
            if paragraph.strip():
                content.append(
                    Paragraph(escape(paragraph), styles["BodyText"])
                )
                content.append(Spacer(1, 8))

    document.build(content)
    buffer.seek(0)

    filename = "".join(
        char if char.isalnum() or char in " -_" else ""
        for char in title
    ).strip() or "novel"

    response = requests.post(
        TG + "/sendDocument",
        data={"chat_id": chat},
        files={
            "document": (
                filename + ".pdf",
                buffer,
                "application/pdf"
            )
        },
        timeout=120
    )
    response.raise_for_status()


def handle(chat, message_text):
    command = message_text.split()[0].split("@")[0].lower()

    if command == "/start":
        send(
            chat,
            "Welcome to your AI Novelist!\n\n"
            "/new — invent a new novel\n"
            "/write — write the next chapter\n"
            "/continue — continue your story\n"
            "/pdf — export your novel as a PDF\n"
            "/status — check your progress\n"
            "/remember — view story continuity memory"
        )

    elif command == "/new":
        new_story(chat)

    elif command in ("/write", "/continue"):
        write_chapter(chat)

    elif command == "/pdf":
        export_pdf(chat)

    elif command == "/status":
        current = project(chat)

        if not current:
            send(chat, "No active novel. Send /new.")
            return

        count = DB.execute(
            "SELECT COUNT(*) FROM chapters WHERE chat=?",
            (chat,)
        ).fetchone()[0]

        send(
            chat,
            f"Novel: {current[0]}\n"
            f"Chapters saved: {count}\n"
            f"Next chapter: {current[3]}"
        )

    elif command == "/remember":
        current = project(chat)

        if not current:
            send(chat, "No active novel. Send /new.")
            return

        latest = DB.execute(
            """
            SELECT number, memory FROM chapters
            WHERE chat=?
            ORDER BY number DESC LIMIT 1
            """,
            (chat,)
        ).fetchone()

        message = f"STORY BIBLE\n{current[1]}\n\n"

        if latest:
            message += (
                f"LATEST CHAPTER {latest[0]} MEMORY:\n{latest[1]}"
            )
        else:
            message += "No chapters written yet."

        send(chat, message)

    else:
        send(
            chat,
            "Use /new, /write, /continue, /pdf, "
            "/status or /remember."
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing in Railway Variables."
        )

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is missing in Railway Variables."
        )

    print("AI Novelist is starting...")

    offset = None

    while True:
        try:
            response = requests.get(
                TG + "/getUpdates",
                params={"timeout": 25, "offset": offset},
                timeout=35
            )

            # Telegram 409 usually means another poll is active.
            if response.status_code == 409:
                print(
                    "Telegram polling conflict: another process may "
                    "be using this bot token. Retrying in 15 seconds."
                )
                time.sleep(15)
                continue

            response.raise_for_status()
            data = response.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message", {})
                chat = message.get("chat", {}).get("id")
                message_text = message.get("text", "")

                if not chat or not message_text:
                    continue

                try:
                    handle(chat, message_text)
                except Exception as exc:
                    print("Request failed:", repr(exc))

                    try:
                        send(
                            chat,
                            "That request failed. Try again shortly. "
                            "If it keeps failing, check the Railway logs."
                        )
                    except Exception as send_error:
                        print("Telegram send failed:", repr(send_error))

        except KeyboardInterrupt:
            print("AI Novelist stopped.")
            break

        except Exception as exc:
            print("Connection error:", repr(exc))
            time.sleep(5)


if __name__ == "__main__":
    main()
