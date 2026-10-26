from typing import Protocol

from google import genai

from app.agent.schemas import AgentDecision


class LLMError(Exception):
    """The LLM call failed: network, timeout, overload, or an invalid reply"""


class LLMClient(Protocol):
    """Anything that can turn a prompt into an AgentDeCision."""

    def decide(self, system: str, user: str) -> AgentDecision:
        """Return the next decision, or raise LLMError if anything goes wrong."""


class GeminiLLMClient:
    """LLMClient that calls the Gemini API."""

    def __init__(self, model: str, timeout: float = 60) -> None:
        self.model = model
        self.timeout = timeout
        self.client = genai.Client()

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
            if not interaction.output_text:
                raise LLMError("Empty response from model")
            return AgentDecision.model_validate_json(interaction.output_text)
        except Exception as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
