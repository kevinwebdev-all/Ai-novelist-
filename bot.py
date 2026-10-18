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

DB.execute("""CREATE TABLE IF NOT EXISTS projects (
 chat INTEGER PRIMARY KEY, title TEXT, bible TEXT,
 outline TEXT, next_chapter INTEGER DEFAULT 1)""")
DB.execute("""CREATE TABLE IF NOT EXISTS chapters (
 chat INTEGER, number INTEGER, text TEXT, memory TEXT,
 PRIMARY KEY(chat, number))""")
DB.commit()

SYSTEM = """You are a world-class novelist and story architect.
Invent original stories without requiring ideas from the user.
Write emotionally intelligent, commercially readable fiction.
Characters need believable motives, flaws, fears, secrets and contradictions.
Show emotion through choices, actions, silence, subtext and dialogue.
Make each character's voice distinct.
Use tension, uncertainty, meaningful consequences and earned twists.
Avoid clichés, filler, repetitive phrasing, melodrama and robotic prose.
Maintain continuity, timeline, relationships and character knowledge.
Never copy existing books. Never promise sales.
Review your writing for emotional depth, logic and continuity before answering."""

def ai(prompt, tokens=3000):
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": tokens
        },
        timeout=180
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def send(chat, text):
    for i in range(0, len(text), 3500):
        r = requests.post(
            TG + "/sendMessage",
            json={"chat_id": chat, "text": text[i:i+3500]},
            timeout=30
        )
        r.raise_for_status()

def project(chat):
    return DB.execute(
        "SELECT title,bible,outline,next_chapter FROM projects WHERE chat=?",
        (chat,)
    ).fetchone()

def new_story(chat):
    send(chat, "Inventing an original novel and building its story bible...")
    result = ai("""Invent three original novel concepts, compare them, and
choose the strongest. Build a complete story bible and four-part plot outline.
Include title, genre, premise, characters, motives, fears, secrets,
relationships, setting, timeline, central conflict, emotional core,
major twists, ending, and continuity rules.
Return this exact format:
TITLE: [title]
BIBLE:
[story bible]
OUTLINE:
[full four-part outline]""", 3000)

    title = "Untitled Novel"
    bible = result
    outline = ""
    section = ""
    collected = {"BIBLE": [], "OUTLINE": []}

    for line in result.splitlines():
        if line.startswith("TITLE:"):
            title = line[6:].strip() or title
        elif line.strip() == "BIBLE:":
            section = "BIBLE"
        elif line.strip() == "OUTLINE:":
            section = "OUTLINE"
        elif section:
            collected[section].append(line)

    if collected["BIBLE"]:
        bible = "\n".join(collected["BIBLE"]).strip()
    if collected["OUTLINE"]:
        outline = "\n".join(collected["OUTLINE"]).strip()

    DB.execute(
        "INSERT OR REPLACE INTO projects VALUES(?,?,?,?,?)",
        (chat, title, bible, outline, 1)
    )
    DB.execute("DELETE FROM chapters WHERE chat=?", (chat,))
    DB.commit()
    send(chat, f"YOUR NEW NOVEL\n\n{title}\n\n{bible}\n\nMASTER OUTLINE:\n{outline}")

def write_chapter(chat):
    p = project(chat)
    if not p:
        send(chat, "Send /new first. I'll invent the story for you.")
        return

    title, bible, outline, number = p
    recent = DB.execute(
        "SELECT number,text,memory FROM chapters WHERE chat=? "
        "ORDER BY number DESC LIMIT 3", (chat,)
    ).fetchall()

    history = "\n\n".join(
        f"CHAPTER {n}:\n{t}\nCONTINUITY MEMORY: {m}"
        for n, t, m in reversed(recent)
    )

    send(chat, f"Writing Chapter {number} of {title}...")
    prompt = f"""NOVEL: {title}
STORY BIBLE:
{bible}
MASTER OUTLINE:
{outline}
PREVIOUS CHAPTERS AND CONTINUITY:
{history or "Chapter 1: establish character, setting and conflict."}

EMOTIONAL INTELLIGENCE:
Track each important character's visible emotion, hidden emotion,
desire, fear, internal contradiction and relationship changes.
Use subtext and distinct voices. Let feelings influence decisions.
Build tension through uncertainty, silence, consequences and pacing.
Avoid explaining every emotion. Do not make characters act against
established knowledge or motives without a believable reason.

Write polished, immersive Chapter {number}, approximately 900-1200 words.
Continue naturally, advance the plot, and do not resolve the entire novel.
Before responding, silently review emotional realism, continuity, pacing,
dialogue and repetitive wording; revise weak passages.

End with this exact separator:
[CONTINUITY MEMORY]
Then record concise factual notes: events, character changes, new facts,
unresolved threads and what should happen next. The notes aren't fiction."""
    result = ai(prompt, 4000)
    parts = result.split("[CONTINUITY MEMORY]", 1)
    chapter = parts[0].strip()
    memory = parts[1].strip() if len(parts) > 1 else (
        "Review chapter before continuing: " + chapter[-1000:]
    )

    DB.execute(
        "INSERT OR REPLACE INTO chapters VALUES(?,?,?,?)",
        (chat, number, chapter, memory)
    )
    DB.execute(
        "UPDATE projects SET next_chapter=? WHERE chat=?",
        (number + 1, chat)
    )
    DB.commit()
    send(chat, f"{title}\nCHAPTER {number}\n\n{chapter}")

def handle(chat, text):
    command = text.split()[0].split("@")[0].lower()

    if command == "/start":
        send(chat, "Welcome to your AI Novelist!\n\n"
             "/new — invent an original novel\n"
             "/write — write the next chapter\n"
             "/continue — continue the story\n"
             "/status — check progress\n"
             "/remember — inspect continuity memory")
    elif command == "/new":
        new_story(chat)
    elif command in ("/write", "/continue"):
        write_chapter(chat)
    elif command == "/status":
        p = project(chat)
        if not p:
            send(chat, "No active novel. Send /new.")
        else:
            count = DB.execute(
                "SELECT COUNT(*) FROM chapters WHERE chat=?", (chat,)
            ).fetchone()[0]
            send(chat, f"Novel: {p[0]}\nChapters saved: {count}\n"
                 f"Next chapter: {p[3]}")
    elif command == "/remember":
        p = project(chat)
        if not p:
            send(chat, "No active novel. Send /new.")
        else:
            row = DB.execute(
                "SELECT number,memory FROM chapters WHERE chat=? "
                "ORDER BY number DESC LIMIT 1", (chat,)
            ).fetchone()
            send(chat, f"STORY BIBLE\n{p[1]}\n\n"
                 + (f"LATEST CHAPTER {row[0]} MEMORY:\n{row[1]}"
                    if row else "No chapters written yet."))
    else:
        send(chat, "Use /new, /write, /continue, /status or /remember.")

def main():
    print("AI Novelist is starting...")
    offset = None
    while True:
        try:
            response = requests.get(
                TG + "/getUpdates",
                params={"timeout": 25, "offset": offset},
                timeout=35
            )
            response.raise_for_status()
            for update in response.json().get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat = message.get("chat", {}).get("id")
                text = message.get("text", "")
                if chat and text:
                    try:
                        handle(chat, text)
                    except Exception as exc:
                        print("Request failed:", str(exc))
                        send(chat, "Something went wrong. Please try again.")
        except KeyboardInterrupt:
            print("AI Novelist stopped.")
            break
        except Exception as exc:
            print("Connection error:", str(exc))
            time.sleep(5)

if __name__ == "__main__":
    main()
