from app.agent.prompts import build_opening_message, build_system_prompt, build_user_message
from app.agent.schemas import Message


def test_start_allows_follow_up_and_next_question(state):
    """On the first topic with no follow-ups used, both are allowed and 'end' is not."""
    assert state.allowed_actions() == ["follow_up", "next_question"]


def test_follow_up_not_allowed_when_used_up(state):
    """With 2/2 follow-ups used, follow_up disappears from the menu (guards the < vs <= bug)."""
    state.follow_ups_on_current = state.max_follow_ups
    assert "follow_up" not in state.allowed_actions()
    assert '"follow_up"' not in build_system_prompt(state)


def test_last_topic_prompt_offers_end_not_next_question(state):
    """On the last topic: 'end' is offered, 'next_question' and the 'Next topic' line are gone."""
    state.current_topic_index = state.last_topic_index
    prompt = build_system_prompt(state)
    assert '"end"' in prompt
    assert '"next_question"' not in prompt
    assert "Next topic" not in prompt


def test_system_prompt_names_current_and_next_topic(state):
    """The model needs both: what to ask about now, and where 'next_question' goes."""
    prompt = build_system_prompt(state)
    assert "Current topic: REST APIs." in prompt
    assert "Next topic: Databases." in prompt


def test_user_message_wraps_candidate_answer_in_transcript(state):
    """Candidate text goes inside <transcript> tags, so the prompt can treat it as data."""
    state.history = [Message(role="candidate", text="I would add an index.")]
    message = build_user_message(state)
    assert "<transcript>\nCandidate: I would add an index.\n</transcript>" in message


def test_opening_message_names_first_topic(state):
    """The opening request asks for a question about topic 1."""
    assert "REST APIs" in build_opening_message(state)
