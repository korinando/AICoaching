from typing import Any, Protocol

from google import genai
from pydantic import BaseModel

from app.agent.schemas import AgentDecision


class LLMError(Exception):
    """The LLM call failed: network, timeout, overload, or an invalid reply"""


class LLMClient(Protocol):
    """Anything that can turn a prompt into an AgentDeCision."""

    def decide(self, system: str, user: str) -> AgentDecision:
        """Return the next decision, or raise LLMError if anything goes wrong."""


class TokenUsage(BaseModel):
    """Running token totals for one client. run_interview makes one client per interview."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage: Any) -> None:
        """Add one API response's `interaction.usage` (None, or fields that may be None)."""
        # Any: the SDK's Usage type lives in a private module (google.genai._gaos), so we
        # don't import it. We only read the 4 fields below.
        self.calls += 1
        if usage is None:
            return
        self.input_tokens += usage.total_input_tokens or 0
        self.output_tokens += usage.total_output_tokens or 0
        self.thought_tokens += usage.total_thought_tokens or 0
        self.total_tokens += usage.total_tokens or 0


class GeminiLLMClient:
    """LLMClient that calls the Gemini API."""

    def __init__(self, model: str, api_key: str | None = None, timeout: float = 60) -> None:
        self.model = model
        self.timeout = timeout
        self.usage = TokenUsage()
        self.client = genai.Client(api_key=api_key)

    def decide(self, system: str, user: str) -> AgentDecision:
        try:
            interaction = self.client.interactions.create(
                model=self.model,
                system_instruction=system,
                input=user,
                generation_config={"thinking_level": "low"},
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": AgentDecision.model_json_schema(),
                },
                timeout=self.timeout,
            )
            # Count before checking the reply: the tokens are spent even if it's unusable.
            self.usage.add(interaction.usage)
            if not interaction.output_text:
                raise LLMError("Empty response from model")
            return AgentDecision.model_validate_json(interaction.output_text)
        except Exception as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
