import pytest

from app.agent.templates import load_templates, new_state


def test_all_templates_load():
    """Every template in templates.json passes validation (a JSON typo fails here first)."""
    templates = load_templates()
    assert "junior_backend" in templates
    assert "junior_frontend" in templates
    assert "junior_ai_engineer" in templates
    for template in templates.values():
        assert len(template.topics) >= 1


def test_new_state_copies_template_settings():
    state = new_state("junior_frontend")
    assert state.role == "Junior Frontend Developer"
    assert state.planned_topics[0] == "HTML/CSS"
    assert state.current_topic_index == 0
    assert state.history == []


def test_data_analyst_template_is_technical():
    state = new_state("junior_data_analyst")
    assert state.role == "Junior Data Analyst"
    assert state.interview_type == "technical"
    assert "SQL" in state.planned_topics


def test_behavioral_template_is_behavioral():
    """A behavioural (HR) interview. The interviewer's prompt shows interview_type, so it must say
    "behavioral", and every topic should get its own main question."""
    state = new_state("junior_behavioral")
    assert state.interview_type == "behavioral"
    assert len(state.planned_topics) == state.max_main_questions


def test_unknown_template_raises_with_valid_ids():
    """The error must say what IS valid, not just what isn't."""
    with pytest.raises(ValueError, match="junior_frontend"):
        new_state("does_not_exist")


def test_new_states_do_not_share_topics():
    """Two interviews from one template must not share one list in memory."""
    a = new_state("junior_backend")
    b = new_state("junior_backend")

    a.planned_topics.append("Hacking")

    assert "Hacking" not in b.planned_topics
