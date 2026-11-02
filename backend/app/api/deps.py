"""Shared FastAPI dependencies: things an endpoint asks for in its parameters."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.agent.interviewer import Interviewer
from app.agent.llm_client import GeminiLLMClient
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import TokenError, decode_token
from app.models import User
from app.speech.storage import AudioStorage, S3AudioStorage

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


@lru_cache
def get_interviewer() -> Interviewer:
    """One Interviewer for the whole server, created on first use.

    Safe to share between users because the Interviewer is stateless (Week 1 design): all
    interview data comes in through the InterviewState. Tests replace this with a fake LLM.
    """
    settings = get_settings()
    llm = GeminiLLMClient(
        model=settings.llm_model, api_key=settings.gemini_api_key.get_secret_value()
    )
    return Interviewer(llm)


InterviewerDep = Annotated[Interviewer, Depends(get_interviewer)]


@lru_cache
def get_audio_storage() -> AudioStorage:
    """One storage client for the whole server, created on first use. Tests use a fake."""
    settings = get_settings()
    return S3AudioStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        bucket=settings.s3_bucket,
    )


AudioStorageDep = Annotated[AudioStorage, Depends(get_audio_storage)]
