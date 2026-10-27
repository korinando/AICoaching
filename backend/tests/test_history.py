from app.agent.history import MAX_RECENT_MESSAGES, earlier_summary, recent_messages
from app.agent.prompts import build_user_message
from app.agent.schemas import Message
from app.agent.templates import new_state


def long_history(count: int) -> list[Message]:
    """count messages alternating interviewer/candidate, numbered so we can tell them apart."""
    return [
        Message(role="interviewer" if i % 2 == 0 else "candidate", text=f"message {i}")
        for i in range(count)
    ]


def test_short_history_is_sent_in_full():
    state = new_state("junior_backend")
    state.history = long_history(4)
    assert recent_messages(state) == state.history


def test_long_history_keeps_only_the_last_messages():
    state = new_state("junior_backend")
    state.history = long_history(20)

    recent = recent_messages(state)

    assert len(recent) == MAX_RECENT_MESSAGES
    assert recent[-1].text == "message 19"
    assert recent[0].text == "message 14"


def test_trimming_never_changes_the_real_history():
    state = new_state("junior_backend")
    state.history = long_history(20)

    build_user_message(state)

    assert len(state.history) == 20


def test_user_message_mentions_omitted_messages():
    state = new_state("junior_backend")
    state.history = long_history(20)
    message = build_user_message(state)
    assert "14 earlier messages not shown" in message
    assert "message 13" not in message


def test_no_summary_on_first_topic():
    state = new_state("junior_backend")
    assert earlier_summary(state) == ""


def test_summary_lists_covered_topics():
    state = new_state("junior_backend")
    state.current_topic_index = 2
    assert earlier_summary(state) == "Topics already covered: REST APIs, Databases."
