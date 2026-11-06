"""The consistency script's arithmetic (Week 6 Step 4). No Gemini."""

from scripts.consistency import answers_in_every_run, find_runs, overall_ranges, ranges, stability
from scripts.evaluate import run_path, save_results
from scripts.label_answers import CRITERIA


def ai(*values: int) -> dict[str, dict]:
    """Scores for the 4 criteria, in order."""
    return {name: {"score": v, "explanation": ""} for name, v in zip(CRITERIA, values, strict=True)}


def test_run_1_keeps_the_plain_name_and_later_runs_are_numbered(tmp_path):
    assert run_path("v1", 1, tmp_path).name == "v1.json"
    assert run_path("v1", 3, tmp_path).name == "v1_run3.json"


def test_runs_are_found_in_order_and_stop_at_a_gap(tmp_path):
    for number, value in ((1, 1), (2, 2), (4, 4)):
        save_results(
            run_path("v1", number, tmp_path), "v1", "m", {1: ai(value, value, value, value)}
        )

    runs = find_runs("v1", tmp_path)

    assert [run[1]["clarity"]["score"] for run in runs] == [1, 2]


def test_other_versions_are_not_mixed_in(tmp_path):
    save_results(run_path("v1", 1, tmp_path), "v1", "m", {1: ai(1, 1, 1, 1)})
    save_results(run_path("v2", 2, tmp_path), "v2", "m", {1: ai(5, 5, 5, 5)})

    assert len(find_runs("v1", tmp_path)) == 1


def test_only_answers_in_every_run_are_compared():
    runs = [{1: ai(3, 3, 3, 3), 2: ai(3, 3, 3, 3)}, {1: ai(3, 3, 3, 3)}]

    assert answers_in_every_run(runs) == [1]


def test_range_is_highest_minus_lowest_for_each_score():
    runs = [{1: ai(1, 3, 3, 5)}, {1: ai(4, 3, 2, 5)}, {1: ai(2, 3, 3, 5)}]

    assert ranges(runs, [1]) == [3, 0, 1, 0]
    assert ranges(runs, [1], ["technical_accuracy"]) == [3]


def test_overall_range_uses_each_runs_average():
    runs = [{1: ai(2, 2, 2, 2)}, {1: ai(3, 3, 3, 4)}]  # averages 2 and 3.25

    assert overall_ranges(runs, [1]) == [1.25]


def test_stability_on_numbers_worked_out_by_hand():
    stats = stability([0, 0, 1, 2])

    assert stats["count"] == 4
    assert stats["identical"] == 50
    assert stats["within_1"] == 75
    assert stats["average_range"] == 0.75
    assert stats["largest"] == 2
