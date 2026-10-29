"""Password hashing and JWT tokens. No database and no FastAPI here, so it's easy to test."""

from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]

# Argon2: a slow, memory-hungry hash on purpose, so guessing millions of passwords from a
# stolen database takes years. Each hash includes its own random salt, so two users with
# the same password get different hashes.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:  # wrong password, or a broken hash
        return False


# A real hash of a random password, used when the email doesn't exist (see auth.login).
DUMMY_HASH = hash_password("not-a-real-password-just-for-timing")


class TokenError(Exception):
    """The token is invalid, expired, or of the wrong type."""


def create_token(user_id: int, token_type: TokenType, expires_in: timedelta | None = None) -> str:
    """A signed token saying "this is user <id>", valid until it expires."""
    settings = get_settings()
    if expires_in is None:
        expires_in = (
            timedelta(minutes=settings.access_token_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_days)
        )
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # "subject": who the token is about (must be a string)
        "type": token_type,  # so a refresh token can't be used as an access token
        "iat": now,  # issued at
        "exp": now + expires_in,  # expiry: PyJWT rejects the token after this
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: TokenType) -> int:
    """Check the signature, expiry and type. Returns the user id or raises TokenError."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            # A fixed list: never let the token choose its own algorithm (e.g. "none").
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "type", "exp"]},
        )
    except jwt.PyJWTError as e:  # bad signature, expired, malformed...
        raise TokenError(str(e)) from e
    if payload["type"] != expected_type:
        raise TokenError(f"Expected a {expected_type} token")
    return int(payload["sub"])
