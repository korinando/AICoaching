from app.agent.prompts import build_system_prompt, build_user_message
from app.agent.schemas import Message
from app.agent.templates import new_state


def test_start_allows_follow_up_and_next_question():
    state = new_state("junior_backend")
    assert state.allowed_actions() == ["follow_up", "next_question"]


def test_last_topic_prompt_offers_end_not_next_question():
    state = new_state("junior_backend")
    state.current_topic_index = state.last_topic_index
    prompt = build_system_prompt(state)
    assert '"end"' in prompt
    assert '"next_question"' not in prompt
    assert "Next topic" not in prompt


def test_user_message_wraps_candidate_answer_in_transcript():
    state = new_state("junior_backend")
    state.history = [Message(role="candidate", text="I would add an index.")]
    message = build_user_message(state)
    assert "<transcript>\nCandidate: I would add an index.\n</transcript>" in message
