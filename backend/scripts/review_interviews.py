"""Export real interviews to read against a checklist (Week 6 Step 6). Read-only, no Gemini calls.

The plan leaves the reading and judging to me. This only writes the transcripts out and flags what
code can check, so I don't miss an obvious one: the judgment calls stay mine.

Run from backend/:
    uv run python -m scripts.review_interviews 13 9 8 10 3
"""

import argparse
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.agent.interviewer import CLOSING_TEXT, OWN_WORDS_TEXT, REPEAT_TEXT
from app.core.db import get_engine
from app.models import InterviewSession

# Personal: my own answers, so kept out of git (see .gitignore). The findings file is committed.
OUT_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "interviewer_review"
MAX_QUESTION_WORDS = 40  # the interviewer's own rule in agent/prompts.py
FIXED_REPLIES = {REPEAT_TEXT, OWN_WORDS_TEXT, CLOSING_TEXT}
# The prompt forbids praising, judging or correcting during the interview.
FEEDBACK_WORDS = re.compile(
    r"\b(great|good|excellent|nice|correct|incorrect|wrong|right|well done|exactly|perfect|"
    r"interesting|impressive|that's true|not quite|actually)\b",
    re.IGNORECASE,
)


def flags(text: str, previous: str | None) -> list[str]:
    """What code can notice about one interviewer turn. A flag is a hint to look, not a verdict."""
    if text in FIXED_REPLIES:
        return []
    found = []
    if text.count("?") > 1:
        found.append(f"{text.count('?')} question marks: more than one question?")
    words = len(text.split())
    if words > MAX_QUESTION_WORDS:
        found.append(f"{words} words: longer than its {MAX_QUESTION_WORDS}-word rule")
    feedback = sorted({m.group(0).lower() for m in FEEDBACK_WORDS.finditer(text)})
    if feedback:
        found.append(f"feedback words: {', '.join(feedback)}")
    if previous is not None and _overlap(text, previous) > 0.6:
        found.append("very similar to its previous question")
    return found


def _overlap(a: str, b: str) -> float:
    words_a, words_b = (
        set(re.findall(r"[a-z']+", a.lower())),
        set(re.findall(r"[a-z']+", b.lower())),
    )
    return len(words_a & words_b) / max(1, min(len(words_a), len(words_b)))


def transcript(session: InterviewSession) -> tuple[str, int]:
    """The interview as Markdown, with flags under each interviewer turn. Returns the flag count."""
    lines = [
        f"# Session {session.id}: {session.template.role}",
        "",
        f"{session.started_at:%Y-%m-%d}, {session.status}, topics: {', '.join(session.template.topics)}",
        "",
    ]
    previous, count = None, 0
    for turn in session.turns:
        who = "Interviewer" if turn.speaker == "interviewer" else "Me"
        lines.append(f"**{turn.turn_index}. {who}:** {turn.text}")
        if turn.speaker == "interviewer":
            for flag in flags(turn.text, previous):
                lines.append(f"> ⚠️ {flag}")
                count += 1
            if turn.text not in FIXED_REPLIES:
                previous = turn.text
        lines.append("")
    return "\n".join(lines), count


def main() -> None:
    parser = argparse.ArgumentParser(description="Export interviews to review.")
    parser.add_argument("sessions", type=int, nargs="+")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with Session(get_engine()) as db:
        for session_id in args.sessions:
            session = db.get(InterviewSession, session_id)
            if session is None:
                print(f"Session {session_id}: not found")
                continue
            text, count = transcript(session)
            path = OUT_DIR / f"session_{session_id}.md"
            path.write_text(text, encoding="utf-8")
            print(f"Session {session_id}: {len(session.turns)} turns, {count} flags -> {path.name}")


if __name__ == "__main__":
    main()
