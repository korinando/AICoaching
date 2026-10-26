from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter

from app.agent.schemas import InterviewState

TEMPLATES_PATH = Path(__file__).parent / "templates.json"


class InterviewTemplate(BaseModel):
    """One interview setup loaded from templates.json.

    Rule: the interviewer asks one main question per topic. The interview ends
    when topics run out or max_main_questions is reached, whichever comes first.
    """

    role: str
    level: str
    interview_type: str
    topics: list[str] = Field(min_length=1)
    max_main_questions: int = Field(ge=1)
    max_follow_ups: int = 2


def load_templates() -> dict[str, InterviewTemplate]:
    """Read templates.json and validate every template in it."""
    text = TEMPLATES_PATH.read_text(encoding="utf-8")
    adapter = TypeAdapter(dict[str, InterviewTemplate])
    return adapter.validate_json(text)


def new_state(template_id: str) -> InterviewState:
    """Create a fresh InterviewState from a template id."""
    templates = load_templates()

    if template_id not in templates:
        available = ", ".join(templates)
        raise ValueError(f"Unknown template '{template_id}'. Available: {available}")

    t = templates[template_id]
    return InterviewState(
        role=t.role,
        level=t.level,
        interview_type=t.interview_type,
        planned_topics=list(t.topics),
        max_main_questions=t.max_main_questions,
        max_follow_ups=t.max_follow_ups,
    )
