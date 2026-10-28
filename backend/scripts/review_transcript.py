"""Print a saved interview transcript and flag possible problems for a human to check.

Run from backend/:
    uv run python -m scripts.review_transcript              # newest transcript
    uv run python -m scripts.review_transcript 2026-10-27_16-15-54.json
"""

import argparse
import json
import re
from pathlib import Path

from app.agent.interviewer import REPEAT_TEXT
from app.agent.schemas import InterviewState

TRANSCRIPTS_DIR = Path(__file__).parent.parent / "transcripts"
MAX_WORDS = 40
# Words that often mean praise, judgement or scoring. Flags are hints, not verdicts:
# "Have a great day" will be flagged too, so read each one.
JUDGEMENT_WORDS = [
    "great",
    "good",
    "excellent",
    "nice",
    "perfect",
    "exactly",
    "well done",
    "correct",
    "incorrect",
    "wrong",
    "right",
    "score",
    "out of 10",
]


def load(name: str | None) -> tuple[Path, InterviewState, dict | None]:
    """Returns the state plus the saved token_usage (None in transcripts made before it existed)."""
    path = TRANSCRIPTS_DIR / name if name else max(TRANSCRIPTS_DIR.glob("*.json"))
    raw = path.read_text(encoding="utf-8")
    return path, InterviewState.model_validate_json(raw), json.loads(raw).get("token_usage")


def flags_for(text: str, previous_question: str | None) -> list[str]:
    flags = []
    words = len(text.split())
    if words > MAX_WORDS:
        flags.append(f"{words} words (max {MAX_WORDS})")
    if text.count("?") > 1:
        flags.append(f"{text.count('?')} questions in one message")
    lower = text.lower()
    found = [w for w in JUDGEMENT_WORDS if re.search(rf"\b{re.escape(w)}\b", lower)]
    if found:
        flags.append(f"judgement words: {', '.join(found)}")
    # REPEAT_TEXT is our own fixed rule text, so repeating it is expected.
    if (
        previous_question
        and text != REPEAT_TEXT
        and text.strip().lower() == previous_question.strip().lower()
    ):
        flags.append("repeats the previous question word for word")
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a saved interview transcript.")
    parser.add_argument("name", nargs="?", help="file name in transcripts/ (default: newest)")
    args = parser.parse_args()

    path, state, usage = load(args.name)
    print(
        f"=== {path.name}: {state.role} | finished={state.finished} | "
        f"{len(state.history)} messages ===\n"
    )

    total_flags = 0
    previous_question = None
    for i, message in enumerate(state.history):
        print(f"{i:2} {message.role[:4].upper()}: {message.text}")
        if message.role == "interviewer":
            for flag in flags_for(message.text, previous_question):
                print(f"     !! {flag}")
                total_flags += 1
            previous_question = message.text
        elif previous_question and previous_question.lower() in message.text.lower():
            print("     !! candidate's answer contains the whole previous question (pasted?)")
            total_flags += 1

    print(
        f"\n{total_flags} flag(s). Flags are hints: read each one and decide if it's a real problem."
    )
    if usage:
        print(
            f"Tokens: {usage['total_tokens']} total in {usage['calls']} calls "
            f"(input {usage['input_tokens']}, output {usage['output_tokens']}, "
            f"thinking {usage['thought_tokens']})"
        )
    else:
        print("Tokens: not recorded (transcript made before token tracking).")


if __name__ == "__main__":
    main()
