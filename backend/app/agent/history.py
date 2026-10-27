from app.agent.schemas import InterviewState, Message

# 6 messages = 3 question/answer pairs: enough for the current topic plus its 2 follow-ups.
MAX_RECENT_MESSAGES = 6


def recent_messages(state: InterviewState) -> list[Message]:
    """The last few messages to send to the LLM. state.history itself is never changed."""
    return state.history[-MAX_RECENT_MESSAGES:]


def omitted_count(state: InterviewState) -> int:
    """How many older messages are left out of the prompt."""
    return max(0, len(state.history) - MAX_RECENT_MESSAGES)


def earlier_summary(state: InterviewState) -> str:
    """A short, deterministic summary of what came before the current topic."""
    covered = state.planned_topics[: state.current_topic_index]
    if state.current_topic_index == 0:
        return ""
    return f"Topics already covered: {', '.join(covered)}."
