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


class UserOut(BaseModel):
    # from_attributes: build it straight from a User database object.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    created_at: datetime
