"""The test set and the labeling tool (Week 6 Steps 1 and 2). No AI and no database here."""

import builtins
import json

import pytest

from scripts import label_answers
from scripts.label_answers import (
    ANSWERS_FILE,
    CRITERIA,
    EVALUATION_DIR,
    StopLabeling,
    ask_score,
    load_answers,
    load_scores,
    save_scores,
)

KINDS_FILE = EVALUATION_DIR / "answer_kinds.json"
ONE_ANSWER_SCORES = dict(zip(CRITERIA, [1, 2, 3, 4], strict=True))


def kinds() -> dict[str, str]:
    data = json.loads(KINDS_FILE.read_text(encoding="utf-8"))
    data.pop("_warning")
    return data


def replies(monkeypatch, *typed):
    """Answers input() with these, in order, and then acts as if the input has ended."""
    queue = iter(typed)

    def fake_input(_prompt=""):
        try:
            return next(queue)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", fake_input)


# --- The test set ------------------------------------------------------------------------------


def test_about_20_answers_with_unique_ids():
    ids = [answer["id"] for answer in load_answers()]

    assert len(ids) == 20
    assert len(set(ids)) == len(ids)


def test_every_answer_has_what_the_scorer_needs():
    for answer in load_answers():
        assert answer["role"] and answer["level"] and answer["question"] and answer["answer"]


def test_the_type_of_answer_is_kept_out_of_the_answers_file():
    """Seeing "strong" or "weak" while scoring would bias me."""
    text = ANSWERS_FILE.read_text(encoding="utf-8")
    for answer in load_answers():
        assert set(answer) == {"id", "role", "level", "question", "answer"}
    assert "confident_but_wrong" not in text


def test_every_answer_has_a_type():
    assert set(kinds()) == {str(answer["id"]) for answer in load_answers()}


def test_the_set_has_the_tricky_cases_the_plan_asks_for():
    found = set(kinds().values())

    assert {"strong", "average", "weak", "confident_but_wrong", "correct_but_rambling"} <= found


def test_strong_and_weak_answers_are_not_grouped_together():
    """Scoring gets easier to guess, and less honest, if the order gives the quality away."""
    in_order = [kinds()[str(answer["id"])] for answer in load_answers()]

    assert in_order != sorted(in_order)
    assert in_order[:5].count("strong") < 5


# --- The labeling tool -------------------------------------------------------------------------


@pytest.mark.parametrize("typed", ["1", "3", "5", " 4 "])
def test_valid_scores_are_accepted(monkeypatch, typed):
    replies(monkeypatch, typed)

    assert ask_score("clarity") == int(typed)


@pytest.mark.parametrize("bad", ["0", "6", "abc", "", "3.5"])
def test_bad_scores_ask_again(monkeypatch, bad):
    replies(monkeypatch, bad, "2")

    assert ask_score("clarity") == 2


def test_r_shows_the_rubric_and_asks_again(monkeypatch, capsys):
    replies(monkeypatch, "r", "3")

    assert ask_score("clarity") == 3
    assert "technical_accuracy" in capsys.readouterr().out


def test_q_stops(monkeypatch):
    replies(monkeypatch, "q")

    with pytest.raises(StopLabeling):
        ask_score("clarity")


def test_scores_survive_saving_and_loading(tmp_path):
    path = tmp_path / "scores.csv"
    scores = {2: ONE_ANSWER_SCORES, 1: ONE_ANSWER_SCORES}

    save_scores(path, scores)

    assert load_scores(path) == scores
    assert path.read_text(encoding="utf-8").splitlines()[1].startswith("1,")  # in id order


def test_no_scores_file_yet_means_no_scores(tmp_path):
    assert load_scores(tmp_path / "missing.csv") == {}


def run_tool(monkeypatch, tmp_path, *typed):
    path = tmp_path / "scores.csv"
    replies(monkeypatch, *typed)
    monkeypatch.setattr("sys.argv", ["label_answers", "--scores", str(path)])
    label_answers.main()
    return path


def test_stopping_keeps_what_was_scored_and_loses_the_rest(monkeypatch, tmp_path):
    path = run_tool(monkeypatch, tmp_path, "1", "2", "3", "4", "5", "q")

    assert load_scores(path) == {1: ONE_ANSWER_SCORES}


def test_carrying_on_starts_at_the_next_answer(monkeypatch, tmp_path, capsys):
    run_tool(monkeypatch, tmp_path, "1", "2", "3", "4", "q")
    capsys.readouterr()

    path = run_tool(monkeypatch, tmp_path, "5", "4", "3", "2", "q")

    assert set(load_scores(path)) == {1, 2}
    assert "Answer 2 of 20" in capsys.readouterr().out


def test_the_tool_never_shows_the_type_of_answer(monkeypatch, tmp_path, capsys):
    run_tool(monkeypatch, tmp_path, *["3"] * (4 * 20))

    out = capsys.readouterr().out
    assert "Done: all 20" in out
    for kind in set(kinds().values()) - {"strong", "average", "weak"}:
        assert kind not in out
