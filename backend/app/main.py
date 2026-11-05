"""FastAPI entry point. Run from backend/:  uv run uvicorn app.main:app --reload"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api import auth, health, sessions, templates, ws
from app.api.deps import get_speech_to_text, get_text_to_speech
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def load_speech_models() -> None:
    """Loading takes seconds, so do it before anyone is waiting. A failure here isn't fatal: the
    first request tries again, and a reply can still go out as text."""
    for name, service in (("voice", get_text_to_speech()), ("Whisper", get_speech_to_text())):
        try:
            service.load()
        except Exception:
            logger.exception("Could not load %s at startup", name)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs once at startup (before yield) and once at shutdown (after yield).
    # Fail fast: a missing or invalid env var stops the server now, not on the first request.
    get_settings()
    # In a thread and not awaited: the server can already answer while this runs.
    loading = asyncio.create_task(asyncio.to_thread(load_speech_models))
    yield
    await loading


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


@app.exception_handler(OperationalError)
def database_unavailable(_request: Request, _error: OperationalError) -> JSONResponse:
    """The database can't be reached. Say so, instead of a confusing 500."""
    return JSONResponse(
        {"detail": "Database unavailable. Please try again in a moment."},
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(sessions.router)
app.include_router(ws.router)
