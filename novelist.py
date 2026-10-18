import os
import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

SYSTEM = """
You are an original fiction novelist, story architect, and meticulous editor.

The user provides NO story ideas. You must invent them yourself.

Create emotionally powerful, commercially readable fiction with:
- Distinct characters with believable motives, flaws, fears, and secrets.
- Natural dialogue, varied sentence rhythms, vivid but restrained details.
- Consequences that carry across chapters.
- Surprising but logically earned twists.
- Emotional depth shown through actions and choices, not melodrama.
- Original plots, characters, scenes, and wording. Never copy existing books.

Avoid generic plots, repetitive phrasing, filler, rushed endings, and robotic prose.
Maintain a consistent story bible, timeline, character knowledge, and relationships.
Never claim that a story guarantees sales or a film adaptation.
"""

def ask_groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.85,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def invent_story():
    return ask_groq("""
Invent three distinctive, emotionally compelling novel concepts
without asking the user for ideas.

Compare their originality, emotional stakes, plot potential, and suitability
for a complete novel. Choose the strongest.

Return:
TITLE:
GENRE:
HOOK:
MAIN CHARACTERS:
CENTRAL CONFLICT:
EMOTIONAL CORE:
FOUR-PART STORY ARC:
ENDING PROMISE:
WHY THIS STORY FEELS DISTINCTIVE:

Avoid copying identifiable existing books or using generic clichés.
""")

if __name__ == "__main__":
    print("AI NOVELIST — STORY ENGINE")
    try:
        print(invent_story())
    except Exception as exc:
        print(f"\nError: {exc}")
