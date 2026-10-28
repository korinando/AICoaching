import pytest

from app.agent.interviewer import CLOSING_TEXT, REPEAT_TEXT, Interviewer
from app.agent.llm_client import LLMError
from app.agent.schemas import InterviewState
from tests.fakes import ANSWER, FakeLLMClient, decision

# --- Follow-up limit ---------------------------------------------------------------------------


def test_follow_ups_are_capped(state):
    """The 3rd follow_up on one topic is overridden to next_question, with our own text."""
    fake = FakeLLMClient([decision("follow_up"), decision("follow_up"), decision("follow_up")])
    interviewer = Interviewer(fake)

    interviewer.handle_answer(state, ANSWER)
    interviewer.handle_answer(state, ANSWER)
    reply = interviewer.handle_answer(state, ANSWER)

    assert state.current_topic_index == 1
    assert state.follow_ups_on_current == 0
    assert "Databases" in reply


# --- Ending ------------------------------------------------------------------------------------


def test_early_end_is_blocked(state):
    """'end' on the first topic is overridden, so a candidate can't talk the interview into ending."""
    fake = FakeLLMClient([decision("end")])

    Interviewer(fake).handle_answer(state, ANSWER)

    assert not state.finished
    assert state.current_topic_index == 1


def test_full_interview_ends_after_last_topic(state):
    """5 topics: 4 answers move forward, the 5th next_question is overridden to end."""
    fake = FakeLLMClient([decision("next_question")] * 5)
    interviewer = Interviewer(fake)

    for _ in range(5):
        reply = interviewer.handle_answer(state, ANSWER)

    assert state.finished
    assert reply == CLOSING_TEXT
    assert len(fake.calls) == 5


def test_interview_ends_at_max_main_questions():
    """Design rule from Step 3: stop at whichever comes first, topics or max_main_questions."""
    state = InterviewState(
        role="Tester",
        level="junior",
        interview_type="technical",
        planned_topics=["A", "B", "C", "D"],
        max_main_questions=2,
    )
    fake = FakeLLMClient([decision("next_question"), decision("next_question")])
    interviewer = Interviewer(fake)

    interviewer.handle_answer(state, ANSWER)  # topic A -> B
    interviewer.handle_answer(state, ANSWER)  # B is the last allowed topic -> overridden to end

    assert state.finished


def test_answer_after_finish_raises(state):
    """Answering a finished interview is a bug in the caller, so it must fail loudly."""
    state.finished = True
    with pytest.raises(RuntimeError, match="already finished"):
        Interviewer(FakeLLMClient([])).handle_answer(state, ANSWER)


# --- Invalid LLM reply: retry and fallback -----------------------------------------------------


def test_retry_once_then_succeed(state):
    """First call fails, second succeeds: the second decision is used."""
    fake = FakeLLMClient([LLMError("boom"), decision("next_question")])

    Interviewer(fake).handle_answer(state, ANSWER)

    assert len(fake.calls) == 2
    assert state.current_topic_index == 1


def test_retry_prompt_includes_the_error(state):
    """The retry tells the model what went wrong, so it can fix its reply."""
    fake = FakeLLMClient([LLMError("bad json"), decision("follow_up")])

    Interviewer(fake).handle_answer(state, ANSWER)

    first_user_message = fake.calls[0][1]
    retry_user_message = fake.calls[1][1]
    assert "bad json" not in first_user_message
    assert "bad json" in retry_user_message


def test_fallback_after_two_failures(state):
    """Two failures: no third call, a safe fallback moves to the next topic."""
    fake = FakeLLMClient([LLMError("boom"), LLMError("boom again")])

    reply = Interviewer(fake).handle_answer(state, ANSWER)

    assert len(fake.calls) == 2
    assert "Databases" in reply
    assert state.current_topic_index == 1


def test_fallback_on_last_topic_ends_interview(state):
    """On the last topic the fallback is 'end', so a dead LLM can't trap the candidate."""
    state.current_topic_index = state.last_topic_index
    fake = FakeLLMClient([LLMError("boom"), LLMError("boom again")])

    reply = Interviewer(fake).handle_answer(state, ANSWER)

    assert state.finished
    assert reply == CLOSING_TEXT


# --- Empty / short answers ---------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["", "   ", "ok", "yes sure"])
def test_short_answers_get_repeat_text(state, answer):
    """Under 3 words: ask again, without calling the LLM and without changing the topic."""
    fake = FakeLLMClient([])

    reply = Interviewer(fake).handle_answer(state, answer)

    assert reply == REPEAT_TEXT
    assert fake.calls == []
    assert state.current_topic_index == 0


def test_short_answers_stop_after_max_retries(state):
    """After 2 repeats the short answer is accepted, so 'ok' forever can't loop forever."""
    fake = FakeLLMClient([decision("follow_up")])
    interviewer = Interviewer(fake)

    first = interviewer.handle_answer(state, "ok")
    second = interviewer.handle_answer(state, "ok")
    third = interviewer.handle_answer(state, "ok")

    assert first == REPEAT_TEXT
    assert second == REPEAT_TEXT
    assert third != REPEAT_TEXT
    assert len(fake.calls) == 1


def test_good_answer_resets_short_answer_counter(state):
    """The 2-repeat budget is per question, not for the whole interview."""
    fake = FakeLLMClient([decision("follow_up")])
    interviewer = Interviewer(fake)

    interviewer.handle_answer(state, "ok")
    assert state.short_answer_retries == 1

    interviewer.handle_answer(state, ANSWER)
    assert state.short_answer_retries == 0


# --- History and start -------------------------------------------------------------------------


def test_turn_adds_answer_and_reply_to_history(state):
    """Each turn records the candidate's answer, then the interviewer's reply, in that order."""
    fake = FakeLLMClient([decision("follow_up", text="Why an index?")])

    Interviewer(fake).handle_answer(state, ANSWER)

    assert [m.role for m in state.history] == ["candidate", "interviewer"]
    assert state.history[0].text == ANSWER
    assert state.history[1].text == "Why an index?"


def test_start_asks_the_llm_opening_question(state):
    """start() uses the LLM's text, adds it to history, and changes no counters."""
    fake = FakeLLMClient([decision("next_question", text="Hello! What is REST?")])

    reply = Interviewer(fake).start(state)

    assert reply == "Hello! What is REST?"
    assert len(state.history) == 1
    assert state.current_topic_index == 0


def test_start_falls_back_when_llm_fails(state):
    """If the LLM is down at the start, a fixed opening question about topic 1 is used."""
    fake = FakeLLMClient([LLMError("down")])

    reply = Interviewer(fake).start(state)

    assert "REST APIs" in reply
    assert len(state.history) == 1
