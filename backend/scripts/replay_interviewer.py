"""Replay real moments from my interviews to today's interviewer, several times each, and count what
it does (Week 6 Step 6). Real Gemini calls. Saves nothing.

Run it before and after changing the interviewer's prompt: one run only says what happened once, and
a prompt change can make things worse.

Run from backend/:
    uv run python -m scripts.replay_interviewer --times 4
    uv run python -m scripts.replay_interviewer --only E      # one moment
"""

import argparse
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agent.schemas import Message
from app.agent.templates import new_state
from app.api.deps import get_interviewer
from app.core.db import get_engine
from app.models import InterviewSession

# Stating what's right or wrong before the question. The prompt forbids correcting the candidate.
CORRECTION = re.compile(
    r"\b(is|are) (typically|usually|actually|generally|normally|in fact|a classic|an example of)\b"
    r"|\b(typically|usually|generally|normally) (uses?|is|are|needs?|requires?)\b"
    r"|\b(that's|that is) (not|incorrect|wrong|right|correct)\b",
    re.IGNORECASE,
)


@dataclass
class Moment:
    name: str
    session_id: int
    answer_turn: int  # the answer given to the interviewer; the turns before it are the history
    topic_index: int
    follow_ups: int
    want: str  # "move on" or "follow up"
    hint_words: tuple[str, ...] = ()  # words that would give the answer away here


MOMENTS = [
    Moment(
        "A. Spam given as unsupervised",
        13,
        3,
        0,
        1,
        "either",
        ("unlabeled", "label", "pre-defined", "predefined", "cluster", "group", "hidden structure"),
    ),
    Moment("B. Reasonable embeddings answer", 13, 9, 2, 0, "move on"),
    Moment("C. Reasonable chunking answer, 1 follow-up used", 13, 11, 2, 1, "move on"),
    Moment("D. Complete, good answer", 10, 1, 0, 0, "move on"),
    Moment("E. Unclear answer", 9, 5, 1, 0, "follow up"),
]


def corrects(text: str) -> bool:
    """Only before the question mark: what comes after is the question itself."""
    before_question = text.rsplit("?", 1)[0].rsplit(".", 1)[0] if "." in text else ""
    return bool(CORRECTION.search(before_question))


def hints(text: str, words: tuple[str, ...]) -> list[str]:
    return [word for word in words if word in text.lower()]


def replay(interviewer, moment: Moment, turns: list) -> tuple[str, str]:
    """One reply to the answer at this moment: (what it did, what it said)."""
    state = new_state("junior_ai_engineer")
    state.current_topic_index = moment.topic_index
    state.follow_ups_on_current = moment.follow_ups
    state.history = [
        Message(role=turn.speaker, text=turn.text) for turn in turns[: moment.answer_turn]
    ]
    text = "".join(interviewer.stream_answer(state, turns[moment.answer_turn].text)).strip()
    if state.current_topic_index > moment.topic_index:
        return "move on", text
    return "follow up", text


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay real moments to the interviewer.")
    parser.add_argument("--times", type=int, default=4, help="replies per moment")
    parser.add_argument("--only", nargs="+", help="only these moments, by letter: A B ...")
    args = parser.parse_args()
    moments = [m for m in MOMENTS if not args.only or m.name[0] in args.only]

    interviewer = get_interviewer()
    with Session(get_engine()) as db:
        sessions = {m.session_id: db.get(InterviewSession, m.session_id).turns for m in moments}
        totals = Counter()
        for moment in moments:
            actions = Counter()
            print(f"\n=== {moment.name} (want: {moment.want})")
            for _ in range(args.times):
                action, text = replay(interviewer, moment, sessions[moment.session_id])
                actions[action] += 1
                problems = []
                if corrects(text):
                    problems.append("CORRECTS")
                    totals["corrections"] += 1
                if found := hints(text, moment.hint_words):
                    problems.append(f"HINTS: {', '.join(found)}")
                    totals["hints"] += 1
                print(f"  [{action}] {' '.join(problems)} {text[:170]}")
            print(f"  -> {dict(actions)}")
            if moment.want != "either":
                totals["as wanted"] += actions[moment.want]
                totals["judged"] += args.times
    print(f"\nDid what I want: {totals['as wanted']} of {totals['judged']}")
    print(
        f"Corrected me: {totals['corrections']}, hinted at the answer: {totals['hints']} (moment A)"
    )


if __name__ == "__main__":
    main()
