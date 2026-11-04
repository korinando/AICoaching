"""Every message on the live interview WebSocket (Week 4 Step 1). The frontend's copy of these
shapes is frontend/lib/wsMessages.ts, and tests/test_ws_messages.py fails if the two differ.

A WebSocket frame is either text or binary, and that decides how it's read:
- Text frame: one JSON object, with a "type" field saying which message it is.
- Binary frame, client to server only: a recording. This is the plan's audio_answer. The
  browser sends the recording as it is, so it has no JSON and no model here.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.api.schemas import MAX_ANSWER_CHARS

# ---- Client to server -----------------------------------------------------------------------


class ClientMessageBase(BaseModel):
    # extra="forbid": this comes from outside the server, so reject what we don't understand.
    model_config = ConfigDict(extra="forbid")


class Auth(ClientMessageBase):
    """Must be the first message. In a message and not the URL, because URLs end up in logs."""

    type: Literal["auth"]
    token: str


class TextAnswer(ClientMessageBase):
    """A typed answer, so the chat box keeps working when POST /answer goes away."""

    type: Literal["text_answer"]
    text: str = Field(max_length=MAX_ANSWER_CHARS)


class EndSession(ClientMessageBase):
    """The user ends the interview early."""

    type: Literal["end_session"]


# discriminator="type": read "type" first and check only that model, so a bad message gets one
# clear error instead of one error per model.
ClientMessage = Annotated[Auth | TextAnswer | EndSession, Field(discriminator="type")]
_client_message = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> ClientMessage:
    """One text frame as a message. Raises pydantic.ValidationError, also on invalid JSON."""
    return _client_message.validate_json(raw)


# ---- Server to client -----------------------------------------------------------------------
# Each has a default type, so the sending code can write Transcript(turn_index=1, text="...").

# A list and not free text, so the frontend can react to a code without reading sentences.
ErrorCode = Literal[
    "unauthorized",  # the token is missing or expired: refresh it and reconnect
    "not_found",  # no such session, or someone else's
    "interview_closed",  # the session is already finished
    "invalid_message",  # the frame couldn't be understood
    "invalid_audio",  # too long, too short, or not audio
    "no_speech",  # silence: ask again, nothing was saved
    "busy",  # an answer is already being processed
    "server_error",  # something failed on our side: trying again may work
]


class Transcript(BaseModel):
    """What Whisper heard (or the typed answer), sent before the interviewer starts on it."""

    type: Literal["transcript"] = "transcript"
    turn_index: int
    text: str


class InterviewerText(BaseModel):
    """One piece of the reply. seq counts from 0 within a turn and matches its AudioChunk."""

    type: Literal["interviewer_text"] = "interviewer_text"
    turn_index: int
    seq: int
    text: str


class AudioChunk(BaseModel):
    """One sentence as a complete WAV file, in base64.

    seq is needed because sentences can finish out of order: TTS runs on several at once.
    """

    type: Literal["audio_chunk"] = "audio_chunk"
    turn_index: int
    seq: int
    audio_base64: str


class TurnComplete(BaseModel):
    """The whole reply has been sent, and the candidate can speak."""

    type: Literal["turn_complete"] = "turn_complete"
    turn_index: int


class AnswerInProgress(BaseModel):
    """Sent on connecting: an answer from before a refresh or a lost connection is still being
    worked on. A turn_complete follows when it's saved."""

    type: Literal["answer_in_progress"] = "answer_in_progress"


class SessionEnded(BaseModel):
    """The interview is over. Week 5 starts generating the report at this point."""

    type: Literal["session_ended"] = "session_ended"
    status: Literal["completed", "abandoned"]


class ErrorMessage(BaseModel):
    """message is written for the user, so it can be shown as it is."""

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


ServerMessage = (
    Transcript
    | InterviewerText
    | AudioChunk
    | TurnComplete
    | AnswerInProgress
    | SessionEnded
    | ErrorMessage
)
