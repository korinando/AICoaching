"""Does the AI judge give the same answer the same scores each time? (Week 6 Step 4)

Compares the runs saved by scripts/evaluate.py for one prompt version. No Gemini calls here: make
the runs first, with the same --label and a different --run:
    uv run python -m scripts.evaluate --label v1 --run 2
    uv run python -m scripts.evaluate --label v1 --run 3

Then, from backend/:
    uv run python -m scripts.consistency --label v1
"""

import argparse
from pathlib import Path
from statistics import mean

from scripts.evaluate import RESULTS_DIR, compare, load_results, run_path, score_pairs
from scripts.label_answers import CRITERIA, SCORES_FILE, load_scores

MIN_RUNS = 2


def find_runs(label: str, folder: Path = RESULTS_DIR) -> list[dict[int, dict]]:
    """Every saved run of this version, in order. Stops at the first run that doesn't exist."""
    runs = []
    number = 1
    while (path := run_path(label, number, folder)).exists():
        runs.append(load_results(path))
        number += 1
    return runs


def answers_in_every_run(runs: list[dict[int, dict]]) -> list[int]:
    """A run cut short by Gemini may be missing answers: only compare what every run has."""
    return sorted(set.intersection(*(set(run) for run in runs)))


def ranges(
    runs: list[dict[int, dict]], ids: list[int], criteria: list[str] = CRITERIA
) -> list[int]:
    """For each answer and criterion: highest score across the runs minus the lowest."""
    return [
        max(run[answer_id][name]["score"] for run in runs)
        - min(run[answer_id][name]["score"] for run in runs)
        for answer_id in ids
        for name in criteria
    ]


def overall_ranges(runs: list[dict[int, dict]], ids: list[int]) -> list[float]:
    """The same for an answer's average across the 4 criteria, which is what a report's
    overall score is made of."""
    averages = [
        [mean(run[answer_id][name]["score"] for name in CRITERIA) for run in runs]
        for answer_id in ids
    ]
    return [max(values) - min(values) for values in averages]


def stability(values: list[int]) -> dict[str, float]:
    return {
        "count": len(values),
        "identical": 100 * mean(v == 0 for v in values),
        "within_1": 100 * mean(v <= 1 for v in values),
        "average_range": mean(values),
        "largest": max(values),
    }


def line(name: str, stats: dict[str, float]) -> str:
    return (
        f"{name:<20} n={stats['count']:<3} the same every time: {stats['identical']:>5.1f}%   "
        f"never more than 1 apart: {stats['within_1']:>5.1f}%   average range: "
        f"{stats['average_range']:.2f}   largest: {stats['largest']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="How much the AI judge varies between runs.")
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    runs = find_runs(args.label)
    if len(runs) < MIN_RUNS:
        raise SystemExit(
            f"Only {len(runs)} run of {args.label}. Make more with: "
            f"uv run python -m scripts.evaluate --label {args.label} --run {len(runs) + 1}"
        )
    ids = answers_in_every_run(runs)
    print(f"=== {args.label}: {len(runs)} runs, {len(ids)} answers in every run")
    print(line("Every score", stability(ranges(runs, ids))))
    for name in CRITERIA:
        print(line(name, stability(ranges(runs, ids, [name]))))
    overall = overall_ranges(runs, ids)
    print(
        f"\nAn answer's average across the 4 criteria moves by {mean(overall):.2f} on average, at most {max(overall):.2f}"
    )

    print("\n=== Agreement with me, run by run (how much the headline number itself moves)")
    mine = load_scores(SCORES_FILE)
    for number, run in enumerate(runs, start=1):
        stats = compare(score_pairs(mine, run, ids=ids))
        print(
            f"Run {number}: within 1 of me {stats['within_1']:.1f}%, exact {stats['exact']:.1f}%, "
            f"average difference {stats['average_difference']:.2f}"
        )

    print("\n=== Least stable answers")
    worst = sorted(
        (
            (answer_id, name, [run[answer_id][name]["score"] for run in runs])
            for answer_id in ids
            for name in CRITERIA
        ),
        key=lambda row: (-(max(row[2]) - min(row[2])), row[0]),
    )[:6]
    for answer_id, name, scores in worst:
        print(f"Answer {answer_id}, {name}: {scores}")


if __name__ == "__main__":
    main()
