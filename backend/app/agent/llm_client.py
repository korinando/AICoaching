from collections.abc import Iterable, Iterator
from typing import Any, Protocol, get_args

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.agent.schemas import Action, AgentDecision


class LLMError(Exception):
    """The LLM call failed: network, timeout, overload, or an invalid reply"""


class LLMClient(Protocol):
    """Anything that can turn a prompt into an AgentDeCision."""

    def decide(self, system: str, user: str) -> AgentDecision:
        """Return the next decision, or raise LLMError if anything goes wrong."""

    def stream(self, system: str, user: str) -> Iterator[str]:
        """Yield the reply piece by piece. Raises LLMError if anything goes wrong."""


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

    def add_stream(self, usage: Any) -> None:
        """The same totals, from a streamed reply's usage_metadata (different field names)."""
        self.calls += 1
        if usage is None:
            return
        self.input_tokens += usage.prompt_token_count or 0
        self.output_tokens += usage.candidates_token_count or 0
        self.thought_tokens += usage.thoughts_token_count or 0
        self.total_tokens += usage.total_token_count or 0


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

    def stream(self, system: str, user: str) -> Iterator[str]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            http_options=types.HttpOptions(timeout=int(self.timeout * 1000)),  # milliseconds
        )
        usage = None
        try:
            for chunk in self.client.models.generate_content_stream(
                model=self.model, contents=user, config=config
            ):
                usage = chunk.usage_metadata or usage
                if chunk.text:  # the last chunk can be empty
                    yield chunk.text
        except Exception as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
        finally:
            self.usage.add_stream(usage)


def _parse_action(line: str) -> Action:
    label, _, value = line.partition(":")
    action = value.strip()
    if label.strip() != "ACTION" or action not in get_args(Action):
        raise LLMError(f"Bad action line: {line!r}")
    return action


def _spoken_text(first: str, chunks: Iterator[str]) -> Iterator[str]:
    yield first
    yield from chunks  # the pieces read_action hasn't touched


def read_action(chunks: Iterable[str]) -> tuple[Action, Iterator[str]]:
    """Read only until the action and the first spoken words have arrived.

    Returns the action and the spoken text, still streaming. Raises LLMError if the reply
    doesn't start with a valid action followed by something to say.
    """
    chunks = iter(chunks)  # a for loop on an iterator continues where the last one stopped
    buffer = ""
    for chunk in chunks:
        buffer += chunk
        first_line, newline, rest = buffer.partition("\n")
        if newline and rest.strip():
            return _parse_action(first_line), _spoken_text(rest.lstrip(), chunks)
    raise LLMError(f"No action and spoken text in the reply: {buffer!r}")
