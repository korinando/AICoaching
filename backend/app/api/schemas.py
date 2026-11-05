"""Shapes of the JSON going in and out of the API. Separate from the database models, so
the API never leaks a column by accident (e.g. password_hash)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

MAX_ANSWER_CHARS = 4000


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


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    turn_index: int
    speaker: str
    text: str
    created_at: datetime
    has_audio: bool  # True: GET /sessions/{id}/turns/{turn_index}/audio plays it


class FirstAudioReport(BaseModel):
    """The browser's measurement. le: a broken client can't store a nonsense number."""

    first_audio_ms: int = Field(ge=0, le=600_000)


class SessionOut(BaseModel):
    """A session with its full transcript: what the chat page shows after a refresh."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    status: str
    started_at: datetime
    ended_at: datetime | None
    turns: list[TurnOut]


class UserOut(BaseModel):
    # from_attributes: build it straight from a User database object.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    created_at: datetime
