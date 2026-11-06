"""Prompt versions (Week 6 Step 5): reports keep using one until another is proven better."""

import pytest

from app.scoring.prompts import (
    PROMPT_ADDITIONS,
    PROMPT_CHANGES,
    PROMPT_VERSION,
    build_scoring_system,
)
from app.scoring.scorer import score_session
from scripts.evaluate import as_interview, score_missing
from tests.fakes import FakeLLMClient
from tests.test_evaluate import ANSWER, judged


def test_reports_use_v1_until_another_version_is_proven():
    assert PROMPT_VERSION == "v1"
    assert build_scoring_system("Role", "junior") == build_scoring_system("Role", "junior", "v1")


def test_v1_has_none_of_the_later_additions():
    v1 = build_scoring_system("Role", "junior", "v1")

    for addition in PROMPT_ADDITIONS["v3"]:
        assert addition not in v1


def test_each_version_adds_to_the_one_before():
    v1 = build_scoring_system("Role", "junior", "v1")
    v2 = build_scoring_system("Role", "junior", "v2")
    v3 = build_scoring_system("Role", "junior", "v3")

    assert len(v1) < len(v2) < len(v3)
    assert all(addition in v3 for addition in PROMPT_ADDITIONS["v2"])


def test_additions_go_before_the_transcription_rules():
    v2 = build_scoring_system("Role", "junior", "v2")

    assert v2.index(PROMPT_ADDITIONS["v2"][0]) < v2.index("The answers were spoken")


def test_every_version_still_has_the_role_and_rubric():
    for version in PROMPT_ADDITIONS:
        assert "Role (junior)" in build_scoring_system("Role", "junior", version)


def test_every_version_describes_its_change():
    assert set(PROMPT_CHANGES) == set(PROMPT_ADDITIONS)


def test_an_unknown_version_is_refused():
    with pytest.raises(ValueError, match="v9"):
        build_scoring_system("Role", "junior", "v9")


def test_the_example_answers_are_not_from_the_test_set():
    """Otherwise the prompt would hand the judge the answers it's tested on."""
    from scripts.label_answers import load_answers

    v3 = build_scoring_system("Role", "junior", "v3")
    for answer in load_answers():
        assert answer["question"] not in v3
        assert answer["answer"][:60] not in v3


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_the_scorer_sends_the_version_asked_for(version):
    llm = FakeLLMClient([judged()])

    score_session(as_interview(ANSWER), llm, version)

    assert llm.calls[0][0] == build_scoring_system(ANSWER["role"], "junior", version)


def test_the_evaluation_scores_with_the_version_asked_for():
    llm = FakeLLMClient([judged()])

    score_missing([ANSWER], {}, llm, lambda r: None, "v3")

    assert llm.calls[0][0] == build_scoring_system(ANSWER["role"], "junior", "v3")
