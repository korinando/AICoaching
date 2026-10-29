"""Shared FastAPI dependencies: things an endpoint asks for in its parameters."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import TokenError, decode_token
from app.models import User

# Reads the "Authorization: Bearer <token>" header. auto_error=False so we send our own
# 401 below instead of FastAPI's default 403. Also adds the "Authorize" button in /docs.
_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The logged-in user, from the access token. Any problem -> 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_token(credentials.credentials, expected_type="access")
    except TokenError:
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None:  # valid token, but the account was deleted since
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
