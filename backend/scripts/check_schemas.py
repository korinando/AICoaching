"""Quick manual check for app/agent/schemas.py. Run from backend/: uv run python -m scripts.check_schemas"""

from pydantic import ValidationError

from app.agent.schemas import AgentDecision, InterviewState

good = AgentDecision.model_validate_json('{"action": "follow_up", "reasoning": "r", "text": "t"}')
print("OK:", good)

state = InterviewState(
    role="Junior Backend", level="junior", interview_type="technical", planned_topics=["Git"]
)
print("OK:", state.model_dump_json())

bad_inputs = {
    "unknown action": '{"action": "dance", "reasoning": "r", "text": "t"}',
    "missing text": '{"action": "end", "reasoning": "r"}',
    "action is a number": '{"action": 5, "reasoning": "r", "text": "t"}',
}
for name, raw in bad_inputs.items():
    try:
        AgentDecision.model_validate_json(raw)
        print(f"NOT rejected ({name})")
    except ValidationError as e:
        print(f"Correctly rejected ({name}): {e.errors()[0]['msg']}")

extra = AgentDecision.model_validate_json(
    '{"action": "end", "reasoning": "r", "text": "t", "mood": "happy"}'
)
print("Extra field accepted, result:", extra)

try:
    state.current_topic_index = -5
    print("Assignment NOT validated (add validate_assignment=True)")
except ValidationError:
    print("Correctly rejected: current_topic_index = -5")
