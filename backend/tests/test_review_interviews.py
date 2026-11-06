"""The automatic flags for the interviewer review (Week 6 Step 6). Read-only, no Gemini."""

from types import SimpleNamespace

import pytest

from app.agent.interviewer import CLOSING_TEXT, REPEAT_TEXT
from scripts.review_interviews import MAX_QUESTION_WORDS, flags, transcript

GOOD = "Can you explain what a database index is?"


def test_a_good_question_has_no_flags():
    assert flags(GOOD, None) == []


def test_two_questions_at_once_are_flagged():
    assert any(
        "question marks" in f for f in flags("What is an index? And when would you add one?", None)
    )


def test_a_question_over_the_word_limit_is_flagged():
    long = " ".join(["word"] * (MAX_QUESTION_WORDS + 1)) + "?"

    assert any("words" in f for f in flags(long, None))


def test_exactly_the_word_limit_is_fine():
    assert flags(" ".join(["word"] * (MAX_QUESTION_WORDS - 1)) + " fine?", None) == []


@pytest.mark.parametrize(
    "text",
    ["Great answer. What is Git?", "That's correct. Next, what is Git?", "Not quite. What is Git?"],
)
def test_praise_or_correction_is_flagged(text):
    assert any("feedback words" in f for f in flags(text, None))


def test_words_inside_other_words_are_not_feedback():
    """ "good" inside "goodbye" and "right" inside "copyright" aren't praise."""
    assert flags("How would you handle copyright in a goodbye email?", None) == []


def test_repeating_the_previous_question_is_flagged():
    assert any(
        "similar" in f for f in flags("Can you explain what a database index is, please?", GOOD)
    )


def test_a_new_question_is_not_flagged_as_a_repeat():
    assert flags("How do you resolve a merge conflict in Git?", GOOD) == []


@pytest.mark.parametrize("fixed", [REPEAT_TEXT, CLOSING_TEXT])
def test_fixed_replies_from_the_rules_are_never_flagged(fixed):
    assert flags(fixed, GOOD) == []


def test_transcript_puts_flags_under_the_interviewer_turn_they_belong_to():
    session = SimpleNamespace(
        id=1,
        status="completed",
        started_at=__import__("datetime").datetime(2026, 11, 6),
        template=SimpleNamespace(role="Junior Backend Developer", topics=["Databases"]),
        turns=[
            SimpleNamespace(turn_index=0, speaker="interviewer", text=GOOD),
            SimpleNamespace(turn_index=1, speaker="candidate", text="Great question, it's fast."),
            SimpleNamespace(turn_index=2, speaker="interviewer", text="Great. Why is it fast?"),
        ],
    )

    text, count = transcript(session)

    assert count == 1  # my own "Great" isn't flagged, only the interviewer's
    lines = text.splitlines()
    flagged = lines.index("**2. Interviewer:** Great. Why is it fast?")
    assert "feedback words: great" in lines[flagged + 1]
