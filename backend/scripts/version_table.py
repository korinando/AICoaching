"""The Step 5 results table: one row per prompt version, ready for the README. No Gemini calls.

Run from backend/:
    uv run python -m scripts.version_table
    uv run python -m scripts.version_table --set holdout
"""

import argparse
from statistics import mean

from app.scoring.prompts import PROMPT_ADDITIONS, PROMPT_CHANGES
from scripts.consistency import answers_in_every_run, find_runs, ranges, stability
from scripts.evaluate import compare, score_pairs
from scripts.label_answers import SETS, load_scores


def row(version: str, mine: dict, answer_set: str = "main") -> list[str] | None:
    runs = find_runs(version, answer_set=answer_set)
    if not runs:
        return None
    ids = answers_in_every_run(runs)
    agreement = [compare(score_pairs(mine, run, ids=ids)) for run in runs]
    steady = stability(ranges(runs, ids)) if len(runs) > 1 else None
    return [
        version,
        PROMPT_CHANGES[version],
        str(len(runs)),
        f"{mean(a['within_1'] for a in agreement):.1f}%",
        f"{mean(a['exact'] for a in agreement):.1f}%",
        f"{mean(a['average_difference'] for a in agreement):.2f}",
        f"{mean(a['bias'] for a in agreement):+.2f}",
        f"{steady['identical']:.1f}%" if steady else "1 run only",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="The prompt versions, side by side.")
    parser.add_argument("--set", choices=SETS, default="main")
    args = parser.parse_args()
    mine = load_scores(SETS[args.set]["scores"])
    header = [
        "Version",
        "Change",
        "Runs",
        "Within 1 of me",
        "Exact",
        "Average difference",
        "AI minus me",
        "Same score every run",
    ]
    rows = [r for version in PROMPT_ADDITIONS if (r := row(version, mine, args.set))]
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join(r) + " |")
    print("\nAgreement numbers are the average over each version's runs.")


if __name__ == "__main__":
    main()
