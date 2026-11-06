"""Score the test answers yourself, one at a time (Week 6 Step 2). No AI runs here.

Your scores are saved after every answer, so you can stop with q and carry on later. Do this before
running the AI on these answers: seeing its scores first would bias yours.

Run from backend/:
    uv run python -m scripts.label_answers                  # the 20 test answers
    uv run python -m scripts.label_answers --set holdout    # the confirmation set
"""

import argparse
import csv
import json
import textwrap
from pathlib import Path

from app.scoring.rubric import RUBRIC

EVALUATION_DIR = Path(__file__).resolve().parents[2] / "evaluation"
ANSWERS_FILE = EVALUATION_DIR / "answers.jsonl"
SCORES_FILE = EVALUATION_DIR / "my_scores.csv"
# main: the 20 answers the prompt versions were tuned on. holdout: new answers to confirm a winner
# on, because a version can fit the answers it was tuned on without really being better.
SETS = {
    "main": {
        "answers": ANSWERS_FILE,
        "scores": SCORES_FILE,
        "kinds": EVALUATION_DIR / "answer_kinds.json",
    },
    "holdout": {
        "answers": EVALUATION_DIR / "holdout_answers.jsonl",
        "scores": EVALUATION_DIR / "holdout_scores.csv",
        "kinds": EVALUATION_DIR / "holdout_kinds.json",
    },
}
CRITERIA = list(RUBRIC)
VALID_SCORES = {"1", "2", "3", "4", "5"}


class StopLabeling(Exception):
    """The user typed q."""


def load_answers(path: Path = ANSWERS_FILE) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_scores(path: Path) -> dict[int, dict[str, int]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as file:
        return {
            int(row["id"]): {name: int(row[name]) for name in CRITERIA}
            for row in csv.DictReader(file)
        }


def save_scores(path: Path, scores: dict[int, dict[str, int]]) -> None:
    """Rewrites the whole file, in id order, so an answer can never appear twice."""
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["id", *CRITERIA])
        writer.writeheader()
        for answer_id in sorted(scores):
            writer.writerow({"id": answer_id, **scores[answer_id]})


def format_rubric() -> str:
    sections = []
    for name, levels in RUBRIC.items():
        lines = [f"  {score}: {meaning}" for score, meaning in levels.items()]
        sections.append(f"{name}\n" + "\n".join(lines))
    return "\n\n".join(sections)


def ask_score(criterion: str) -> int:
    while True:
        reply = input(f"  {criterion} (1-5, r = rubric, q = stop): ").strip().lower()
        if reply == "q":
            raise StopLabeling
        if reply == "r":
            print(f"\n{format_rubric()}\n")
        elif reply in VALID_SCORES:
            return int(reply)
        else:
            print("  Please type a number from 1 to 5.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the test answers yourself.")
    parser.add_argument("--set", choices=SETS, default="main", help="which answers to score")
    parser.add_argument("--scores", type=Path, help="where to save (default: the set's file)")
    args = parser.parse_args()

    answers = load_answers(SETS[args.set]["answers"])
    path = args.scores or SETS[args.set]["scores"]
    scores = load_scores(path)
    print(f"{format_rubric()}\n")
    print("Judge what each answer shows. The answers were typed or spoken, so ignore odd words.")
    try:
        for answer in answers:
            if answer["id"] in scores:
                continue
            print(f"\n--- Answer {len(scores) + 1} of {len(answers)} ({answer['role']}, junior)")
            print(textwrap.fill(f"Question: {answer['question']}", 90))
            print(textwrap.fill(f"Answer: {answer['answer']}", 90))
            scores[answer["id"]] = {name: ask_score(name) for name in CRITERIA}
            save_scores(path, scores)
    except (StopLabeling, EOFError):
        print(f"\nStopped. Saved {len(scores)} of {len(answers)}. Run this again to carry on.")
        return
    print(f"\nDone: all {len(answers)} saved in {path}")


if __name__ == "__main__":
    main()
