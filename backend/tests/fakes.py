import io
import wave
from collections.abc import Iterator

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

    def stream(self, system: str, user: str) -> Iterator[str]:
        self.calls.append((system, user))
        if not self.script:
            raise AssertionError("FakeLLMClient was called more times than scripted")
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        yield from result  # a list of chunks


class FakeAudioStorage:
    """AudioStorage for tests: keeps files in a dict, or fails on demand."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.error: Exception | None = None

    def save(self, key: str, data: bytes, content_type: str) -> None:
        if self.error:
            raise self.error
        self.files[key] = (data, content_type)

    def load(self, key: str) -> bytes:
        if self.error:
            raise self.error
        return self.files[key][0]


class FakeTextToSpeech:
    """TextToSpeech for tests: "speaks" by returning the text as bytes, or fails on demand."""

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        if self.error:
            raise self.error
        return spoken(text)


class FakeSpeechToText:
    """SpeechToText for tests: returns a set text, records what it was given, or fails."""

    def __init__(self, text: str = ANSWER) -> None:
        self.text = text
        self.error: Exception | None = None
        self.calls: list[bytes] = []

    def transcribe(self, wav: bytes) -> str:
        self.calls.append(wav)
        if self.error:
            raise self.error
        return self.text


def decision(action: Action, text: str = "Scripted reply.") -> AgentDecision:
    """A scripted AgentDecision for FakeLLMClient."""
    return AgentDecision(action=action, reasoning="test", text=text)


def streamed(action: Action, text: str = "Scripted reply.") -> list[str]:
    """A scripted streaming reply for FakeLLMClient: the ACTION line, then the text."""
    return [f"ACTION: {action}\n{text}"]


def spoken(text: str) -> bytes:
    """What FakeTextToSpeech returns: a real WAV file, whose samples are the text's bytes."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setparams((1, 1, 16_000, 0, "NONE", "not compressed"))
        wav_file.writeframes(text.encode())
    return buffer.getvalue()
