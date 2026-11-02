"""Shapes of the JSON going in and out of the API. Separate from the database models, so
the API never leaks a column by accident (e.g. password_hash)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr  # format checked by email-validator: "abc" is rejected with a 422
    # max_length: Argon2 hashes any length, but a 1 MB "password" would waste CPU.
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    role: str
    level: str
    interview_type: str
    topics: list[str]
    max_main_questions: int


class SessionCreate(BaseModel):
    template_id: int


class AnswerRequest(BaseModel):
    # No min_length: empty and very short answers are the agent's job ("say a bit more").
    # max_length stops a huge paste from filling the prompt and the database.
    text: str = Field(max_length=4000)


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    turn_index: int
    speaker: str
    text: str
    created_at: datetime


class SessionOut(BaseModel):
    """A session with its full transcript: what the chat page shows after a refresh."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    status: str
    started_at: datetime
    ended_at: datetime | None
    turns: list[TurnOut]


class AnswerOut(BaseModel):
    """Only the new turns (the answer as saved + the reply), so the chat can append them."""

    status: str
    turns: list[TurnOut]


class AudioReceived(BaseModel):
    """Steps 2-3: proof the recording arrived and was decoded. Step 5 answers with turns."""

    size_bytes: int
    content_type: str
    duration_seconds: float  # measured by decoding the audio, not trusted from the browser
    wav_bytes: int  # size after converting to 16 kHz mono WAV
    audio_key: str  # where the WAV is stored; Step 5 saves it in turns.audio_url


class UserOut(BaseModel):
    # from_attributes: build it straight from a User database object.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    created_at: datetime
