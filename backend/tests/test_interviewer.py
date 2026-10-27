from app.agent.interviewer import REPEAT_TEXT, Interviewer
from app.agent.llm_client import LLMError
from app.agent.schemas import AgentDecision
from app.agent.templates import new_state
from tests.fakes import FakeLLMClient

ANSWER = "I would add an index to the table."


def decision(action: str, text: str = "Scripted reply.") -> AgentDecision:
    return AgentDecision(action=action, reasoning="test", text=text)


def test_follow_ups_are_capped():
    fake = FakeLLMClient([decision("follow_up"), decision("follow_up"), decision("follow_up")])
    state = new_state("junior_backend")
    interviewer = Interviewer(fake)

    interviewer.handle_answer(state, ANSWER)
    interviewer.handle_answer(state, ANSWER)
    reply = interviewer.handle_answer(state, ANSWER)  # 3rd follow_up must be overridden

    assert state.current_topic_index == 1
    assert state.follow_ups_on_current == 0
    assert "Databases" in reply


def test_retry_once_then_succeed():
    fake = FakeLLMClient([LLMError("boom"), decision("next_question")])
    state = new_state("junior_backend")

    Interviewer(fake).handle_answer(state, ANSWER)

    assert len(fake.calls) == 2
    assert state.current_topic_index == 1


def test_fallback_after_two_failures():
    fake = FakeLLMClient([LLMError("boom"), LLMError("boom again")])
    state = new_state("junior_backend")

    reply = Interviewer(fake).handle_answer(state, ANSWER)

    assert "Databases" in reply
    assert state.current_topic_index == 1


def test_short_answer_does_not_call_llm():
    fake = FakeLLMClient([])
    state = new_state("junior_backend")

    reply = Interviewer(fake).handle_answer(state, "ok")

    assert reply == REPEAT_TEXT
    assert len(fake.calls) == 0


def test_early_end_is_blocked():
    fake = FakeLLMClient([decision("end")])
    state = new_state("junior_backend")

    Interviewer(fake).handle_answer(state, ANSWER)

    assert not state.finished
    assert state.current_topic_index == 1
