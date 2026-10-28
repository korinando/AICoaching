from app.agent.schemas import Action, AgentDecision

# A normal answer: long enough (3+ words) to pass the short-answer check and reach the LLM.
ANSWER = "I would add an index to the table."


class FakeLLMClient:
    """LLMClient for tests: returns scripted results in order and records every call."""

    def __init__(self, script: list[AgentDecision | Exception]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, str]] = []

    def decide(self, system: str, user: str) -> AgentDecision:
        self.calls.append((system, user))
        if not self.script:
            raise AssertionError("FakeLLMClient was called more times than scripted")
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def decision(action: Action, text: str = "Scripted reply.") -> AgentDecision:
    """A scripted AgentDecision for FakeLLMClient."""
    return AgentDecision(action=action, reasoning="test", text=text)
