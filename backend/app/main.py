"""FastAPI entry point. Run from backend/:  uv run uvicorn app.main:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, sessions, templates
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs once at startup (before yield) and once at shutdown (after yield).
    # Fail fast: a missing or invalid env var stops the server now, not on the first request.
    get_settings()
    yield


app = FastAPI(title="AI Mock Interview Coach", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(sessions.router)
