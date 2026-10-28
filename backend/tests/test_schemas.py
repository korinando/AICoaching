import pytest
from pydantic import ValidationError

from app.agent.schemas import AgentDecision


def test_decision_accepts_valid_json():
    raw = '{"action": "follow_up", "reasoning": "r", "text": "Why?"}'
    assert AgentDecision.model_validate_json(raw).action == "follow_up"


@pytest.mark.parametrize(
    "raw",
    [
        '{"action": "dance", "reasoning": "r", "text": "t"}',  # unknown action
        '{"action": "end", "reasoning": "r"}',  # missing text
        '```json\n{"action": "end", "reasoning": "r", "text": "t"}\n```',  # code fences (Step 2)
    ],
)
def test_decision_rejects_bad_llm_output(raw):
    """Everything the LLM can get wrong must fail here, so the interviewer can retry."""
    with pytest.raises(ValidationError):
        AgentDecision.model_validate_json(raw)


def test_state_rejects_negative_counter(state):
    """validate_assignment=True: a bug that sets a counter below 0 fails immediately."""
    with pytest.raises(ValidationError):
        state.current_topic_index = -1
