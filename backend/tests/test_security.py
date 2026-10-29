"""Hashing and tokens on their own: no database, no HTTP."""

from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    JWT_ALGORITHM,
    TokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_verifies_and_hides_the_password():
    hashed = hash_password("correct horse")
    assert "correct horse" not in hashed
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong horse", hashed)


def test_same_password_gives_different_hashes():
    """Random salt: equal passwords can't be spotted by comparing hashes."""
    assert hash_password("same-password") != hash_password("same-password")


def test_token_round_trip():
    assert decode_token(create_token(42, "access"), expected_type="access") == 42


def test_refresh_token_is_not_an_access_token():
    """Otherwise a long-lived refresh token could be used directly on every endpoint."""
    with pytest.raises(TokenError, match="access"):
        decode_token(create_token(42, "refresh"), expected_type="access")


def test_expired_token_is_rejected():
    token = create_token(42, "access", expires_in=timedelta(seconds=-1))
    with pytest.raises(TokenError, match="expired"):
        decode_token(token, expected_type="access")


def test_token_signed_with_another_secret_is_rejected():
    """Anyone can create a token; only ours carry our signature."""
    forged = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999},
        "an-attackers-own-secret-that-is-long-enough",
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_token(forged, expected_type="access")


def test_unsigned_token_is_rejected():
    """The classic "alg: none" attack: a token with no signature at all."""
    unsigned = jwt.encode({"sub": "1", "type": "access", "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(TokenError):
        decode_token(unsigned, expected_type="access")
