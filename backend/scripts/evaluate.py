"""How well does the AI judge agree with me? (Week 6 Step 3)

Runs the real scorer on each test answer, as a one-answer interview, and compares with my own scores.
Results are saved after every answer, so a Gemini failure loses nothing: run it again to carry on.
Refuses to run until I've scored everything, because the AI's scores would bias mine.

Run from backend/:
    uv run python -m scripts.evaluate --label v1          # scores what's missing, then reports
    uv run python -m scripts.evaluate --label v1 --report # only the report: no Gemini calls
    uv run python -m scripts.evaluate --label v1 --run 2  # the same again, for consistency
"""

import argparse
import json
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

from app.agent.llm_client import LLMClient, LLMError
from app.scoring.prompts import PROMPT_ADDITIONS
from app.scoring.rubric import RUBRIC, RUBRIC_VERSION
from app.scoring.scorer import score_session
from scripts.label_answers import CRITERIA, EVALUATION_DIR, SETS, load_answers, load_scores

RESULTS_DIR = EVALUATION_DIR / "results"
LAZY_SCORE = 3  # a judge that says 3 to everything, without reading the answer


def run_path(label: str, run: int, folder: Path = RESULTS_DIR, answer_set: str = "main") -> Path:
    """Run 1 keeps the plain name, so the first results don't move when more runs are added. The
    main set keeps its old names too, and other sets get their name in front."""
    prefix = "" if answer_set == "main" else f"{answer_set}_"
    return folder / (f"{prefix}{label}.json" if run == 1 else f"{prefix}{label}_run{run}.json")


def as_interview(answer: dict) -> SimpleNamespace:
    """What score_session reads from a session, for an interview of this one answer."""
    return SimpleNamespace(
        turns=[
            SimpleNamespace(speaker="interviewer", text=answer["question"]),
            SimpleNamespace(speaker="candidate", text=answer["answer"]),
        ],
        template=SimpleNamespace(role=answer["role"], level=answer["level"]),
    )


def missing_scores(answers: list[dict], mine: dict[int, dict[str, int]]) -> list[int]:
    return [answer["id"] for answer in answers if answer["id"] not in mine]


def load_results(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(answer_id): result for answer_id, result in data["answers"].items()}


def save_results(path: Path, label: str, model: str, results: dict[int, dict]) -> None:
    path.parent.mkdir(exist_ok=True)
    data = {
        "label": label,
        "rubric_version": RUBRIC_VERSION,
        "model": model,
        "answers": {str(answer_id): results[answer_id] for answer_id in sorted(results)},
    }
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def score_missing(
    answers: list[dict], results: dict[int, dict], llm: LLMClient, save, prompt_version: str = "v1"
) -> list[tuple[int, str]]:
    """Scores what isn't done yet. A failed answer is skipped and tried on the next run."""
    failures = []
    for answer in answers:
        if answer["id"] in results:
            continue
        try:
            report = score_session(as_interview(answer), llm, prompt_version)
        except LLMError as e:
            failures.append((answer["id"], str(e)[:120]))
            print(f"Answer {answer['id']}: failed, try again later: {str(e)[:120]}", flush=True)
            continue
        results[answer["id"]] = {
            name: {
                "score": report["scores"][name]["score"],
                "explanation": report["scores"][name]["explanation"],
            }
            for name in CRITERIA
        }
        save(results)
        print(f"Answer {answer['id']}: scored", flush=True)
    return failures


def compare(pairs: list[tuple[int, int]]) -> dict[str, float]:
    """pairs: (my score, the other's score)."""
    differences = [other - mine for mine, other in pairs]
    return {
        "count": len(pairs),
        "within_1": 100 * mean(abs(d) <= 1 for d in differences),
        "exact": 100 * mean(d == 0 for d in differences),
        "average_difference": mean(abs(d) for d in differences),
        # Above 0: more generous than me. Below 0: harsher. The two can cancel out in an average, which
        # is why the difference above ignores the sign.
        "bias": mean(differences),
    }


def score_pairs(
    mine: dict[int, dict[str, int]],
    results: dict[int, dict],
    criteria: list[str] = CRITERIA,
    ids: list[int] | None = None,
) -> list[tuple[int, int]]:
    return [
        (mine[answer_id][name], results[answer_id][name]["score"])
        for answer_id in (ids if ids is not None else sorted(results))
        if answer_id in results
        for name in criteria
    ]


def lazy_pairs(mine: dict[int, dict[str, int]], results: dict[int, dict]) -> list[tuple[int, int]]:
    return [(mine[answer_id][name], LAZY_SCORE) for answer_id in results for name in CRITERIA]


def spread(scores: list[int]) -> int:
    return max(scores) - min(scores)


def average_spread(rows: list[dict[str, int]]) -> float:
    """How far apart one answer's 4 scores are. Near 0: one impression is setting all of them."""
    return mean(spread([row[name] for name in CRITERIA]) for row in rows)


def biggest_disagreements(
    mine: dict[int, dict[str, int]], results: dict[int, dict], limit: int = 6
) -> list[dict]:
    rows = [
        {
            "id": answer_id,
            "criterion": name,
            "mine": mine[answer_id][name],
            "ai": result[name]["score"],
            "explanation": result[name]["explanation"],
        }
        for answer_id, result in results.items()
        for name in CRITERIA
    ]
    rows.sort(key=lambda row: (-abs(row["ai"] - row["mine"]), row["id"]))
    return rows[:limit]


def line(name: str, stats: dict[str, float]) -> str:
    return (
        f"{name:<28} n={stats['count']:<3} within 1: {stats['within_1']:>5.1f}%   "
        f"exact: {stats['exact']:>5.1f}%   average difference: {stats['average_difference']:.2f}   "
        f"AI minus me: {stats['bias']:+.2f}"
    )


def print_report(
    mine: dict[int, dict[str, int]], results: dict[int, dict], kinds: dict[str, str]
) -> None:
    print(f"\n=== {len(results)} answers, {len(results) * len(CRITERIA)} scores")
    print(line("AI judge", compare(score_pairs(mine, results))))
    print(line(f"Lazy judge (always {LAZY_SCORE})", compare(lazy_pairs(mine, results))))

    print("\n=== By criterion")
    for name in RUBRIC:
        print(line(name, compare(score_pairs(mine, results, [name]))))

    print("\n=== By type of answer")
    for kind in sorted(set(kinds.values())):
        ids = [int(answer_id) for answer_id, value in kinds.items() if value == kind]
        pairs = score_pairs(mine, results, ids=ids)
        if pairs:
            print(line(kind, compare(pairs)))

    print("\n=== Do the 4 scores on one answer really differ? (the halo effect)")
    my_rows = [mine[answer_id] for answer_id in results]
    ai_rows = [{name: result[name]["score"] for name in CRITERIA} for result in results.values()]
    print(
        f"Average gap between an answer's highest and lowest score: me {average_spread(my_rows):.2f}, AI {average_spread(ai_rows):.2f}"
    )
    identical = sum(spread(list(row.values())) == 0 for row in ai_rows)
    print(
        f"Answers with the same number on all 4: me {sum(spread(list(r.values())) == 0 for r in my_rows)}, AI {identical}"
    )

    print("\n=== Biggest disagreements")
    for row in biggest_disagreements(mine, results):
        print(f"Answer {row['id']}, {row['criterion']}: me {row['mine']}, AI {row['ai']}")
        print(f"  AI's reason: {row['explanation'][:230]}")


def load_kinds(answer_set: str = "main") -> dict[str, str]:
    data = json.loads(SETS[answer_set]["kinds"].read_text(encoding="utf-8"))
    data.pop("_warning", None)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare the AI judge with my own scores.")
    parser.add_argument("--label", required=True, help="the prompt version, such as v1 or v2")
    parser.add_argument("--report", action="store_true", help="only the report: no Gemini calls")
    parser.add_argument("--run", type=int, default=1, help="another run of the same version")
    parser.add_argument("--set", choices=SETS, default="main", help="which answers to score")
    args = parser.parse_args()

    answers = load_answers(SETS[args.set]["answers"])
    mine = load_scores(SETS[args.set]["scores"])
    missing = missing_scores(answers, mine)
    if missing:
        raise SystemExit(
            f"Score these yourself first: {missing}. "
            f"uv run python -m scripts.label_answers --set {args.set}"
        )

    if args.label not in PROMPT_ADDITIONS:
        raise SystemExit(f"No prompt version {args.label!r}. Known: {list(PROMPT_ADDITIONS)}")
    path = run_path(args.label, args.run, answer_set=args.set)
    results = load_results(path)
    if not args.report:
        # Here and not at the top: --report needs no Gemini key, and importing jobs loads a lot.
        from app.core.config import get_settings
        from app.workers.jobs import _llm

        model = get_settings().llm_model
        failures = score_missing(
            answers,
            results,
            _llm(),
            lambda r: save_results(path, args.label, model, r),
            args.label,
        )
        if failures:
            print(f"\n{len(failures)} failed. Run the same command later to score only those.")
    if results:
        print_report(mine, results, load_kinds(args.set))


if __name__ == "__main__":
    main()
