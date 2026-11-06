"""The evaluation script's arithmetic (Week 6 Step 3). No Gemini: a wrong formula here would give
believable, wrong numbers, and nothing else would notice."""

import pytest

from app.agent.llm_client import LLMError
from app.scoring import scorer
from app.scoring.rubric import RUBRIC
from app.scoring.schemas import JudgeReply
from scripts.evaluate import (
    as_interview,
    average_spread,
    biggest_disagreements,
    compare,
    lazy_pairs,
    load_results,
    missing_scores,
    save_results,
    score_missing,
    score_pairs,
    spread,
)
from scripts.label_answers import CRITERIA
from tests.fakes import FakeLLMClient

ANSWER = {
    "id": 1,
    "role": "Junior Backend Developer",
    "level": "junior",
    "question": "What is an index?",
    "answer": "It makes reads faster.",
}


def scores(value: int) -> dict[str, int]:
    return dict.fromkeys(CRITERIA, value)


def ai(value: int) -> dict[str, dict]:
    return {name: {"score": value, "explanation": f"Why {name}."} for name in CRITERIA}


def judged(score: int = 3) -> JudgeReply:
    example = {"question_number": 1, "quote": "makes reads faster", "comment": "That helped."}
    overall = {
        name: {"examples": [example], "explanation": f"Why {name}.", "score": score}
        for name in RUBRIC
    }
    return JudgeReply(overall=overall, strengths=["Clear"], improvements=["Depth"])


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(scorer, "RETRY_WAIT_S", 0)


# --- The numbers -------------------------------------------------------------------------------


def test_compare_on_numbers_worked_out_by_hand():
    stats = compare([(3, 3), (3, 4), (3, 5), (5, 1)])  # differences: 0, +1, +2, -4

    assert stats["count"] == 4
    assert stats["within_1"] == 50  # 0 and +1
    assert stats["exact"] == 25  # only 0
    assert stats["average_difference"] == 7 / 4  # (0 + 1 + 2 + 4) / 4
    assert stats["bias"] == -1 / 4  # (0 + 1 + 2 - 4) / 4


def test_being_generous_is_a_positive_bias_and_harsh_is_negative():
    assert compare([(2, 4)])["bias"] == 2
    assert compare([(4, 2)])["bias"] == -2


def test_errors_in_both_directions_cancel_in_bias_but_not_in_the_difference():
    stats = compare([(3, 5), (3, 1)])

    assert stats["bias"] == 0
    assert stats["average_difference"] == 2


def test_within_1_counts_exactly_one_point_away_and_not_two():
    assert compare([(3, 4)])["within_1"] == 100
    assert compare([(3, 2)])["within_1"] == 100
    assert compare([(3, 5)])["within_1"] == 0


def test_pairs_are_my_score_then_the_ais_for_each_criterion():
    pairs = score_pairs({1: scores(2)}, {1: ai(4)})

    assert pairs == [(2, 4)] * len(CRITERIA)


def test_pairs_can_be_limited_to_a_criterion_and_to_some_answers():
    mine = {1: scores(1), 2: scores(2)}
    results = {1: ai(3), 2: ai(4)}

    assert score_pairs(mine, results, ["clarity"]) == [(1, 3), (2, 4)]
    assert score_pairs(mine, results, ["clarity"], ids=[2]) == [(2, 4)]


def test_an_answer_the_ai_has_not_scored_is_not_counted():
    assert score_pairs({1: scores(2), 2: scores(2)}, {1: ai(2)}) == [(2, 2)] * len(CRITERIA)


def test_the_lazy_judge_always_says_3():
    assert lazy_pairs({1: scores(5)}, {1: ai(1)}) == [(5, 3)] * len(CRITERIA)


def test_spread_is_the_gap_between_highest_and_lowest():
    assert spread([2, 2, 2, 2]) == 0
    assert spread([1, 3, 2, 5]) == 4


def test_average_spread_is_across_answers():
    rows = [scores(3), dict(zip(CRITERIA, [1, 2, 3, 3], strict=True))]

    assert average_spread(rows) == 1  # (0 + 2) / 2


def test_biggest_disagreements_come_first_whichever_direction():
    mine = {1: scores(3), 2: scores(3), 3: scores(3)}
    results = {1: ai(4), 2: ai(1), 3: ai(3)}

    top = biggest_disagreements(mine, results, limit=1)[0]

    assert (top["id"], top["mine"], top["ai"]) == (2, 3, 1)


# --- Running the scorer ------------------------------------------------------------------------


def test_each_answer_is_scored_as_a_one_answer_interview():
    interview = as_interview(ANSWER)

    assert [(t.speaker, t.text) for t in interview.turns] == [
        ("interviewer", ANSWER["question"]),
        ("candidate", ANSWER["answer"]),
    ]
    assert interview.template.role == ANSWER["role"]
    assert interview.template.level == "junior"


def test_scoring_keeps_the_scores_and_saves_after_each_answer():
    saved = []

    failures = score_missing(
        [ANSWER], {}, FakeLLMClient([judged(4)]), lambda r: saved.append(dict(r))
    )

    assert failures == []
    assert saved[0][1]["clarity"] == {"score": 4, "explanation": "Why clarity."}


def test_an_answer_already_scored_costs_no_call():
    llm = FakeLLMClient([])

    score_missing([ANSWER], {1: ai(3)}, llm, lambda r: None)

    assert llm.calls == []


def test_gemini_failing_skips_the_answer_and_keeps_going():
    second = {**ANSWER, "id": 2}
    llm = FakeLLMClient([LLMError("503"), LLMError("503"), LLMError("503"), judged(4)])
    results = {}

    failures = score_missing([ANSWER, second], results, llm, lambda r: None)

    assert [answer_id for answer_id, _reason in failures] == [1]
    assert set(results) == {2}


def test_a_bad_quote_from_gemini_is_retried_inside_the_scorer():
    bad = judged()
    bad.overall.depth.examples[0].quote = "never said this"
    results = {}

    score_missing([ANSWER], results, FakeLLMClient([bad, judged()]), lambda r: None)

    assert set(results) == {1}


# --- Files -------------------------------------------------------------------------------------


def test_results_survive_saving_and_loading(tmp_path):
    path = tmp_path / "results" / "v1.json"

    save_results(path, "v1", "test-model", {2: ai(4), 1: ai(3)})

    assert load_results(path) == {1: ai(3), 2: ai(4)}


def test_no_results_yet_means_nothing_scored(tmp_path):
    assert load_results(tmp_path / "missing.json") == {}


def test_missing_scores_names_what_i_still_have_to_score():
    answers = [ANSWER, {**ANSWER, "id": 2}]

    assert missing_scores(answers, {1: scores(3)}) == [2]
    assert missing_scores(answers, {1: scores(3), 2: scores(3)}) == []
