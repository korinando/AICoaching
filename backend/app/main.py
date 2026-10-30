"""FastAPI entry point. Run from backend/:  uv run uvicorn app.main:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, sessions, templates
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs once at startup (before yield) and once at shutdown (after yield).
    # Fail fast: a missing or invalid env var stops the server now, not on the first request.
    get_settings()
    yield


app = FastAPI(title="AI Mock Interview Coach", lifespan=lifespan)

# CORS: browsers block a page on one origin (localhost:3000) from reading responses from
# another (localhost:8000) unless the server says it's allowed. Only the listed origins are.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    # The login token travels in the Authorization header, not in cookies, so the browser
    # never needs to send cookies here.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(sessions.router)
