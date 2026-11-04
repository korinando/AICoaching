"""Database connection: one engine for the app, one session per request."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings

CONNECT_TIMEOUT_S = 3


@lru_cache
def get_engine() -> Engine:
    """The engine holds a pool of open connections. Created on first use, not at import,
    so importing the app (e.g. in tests) doesn't need a database."""
    # pool_pre_ping: test a pooled connection before using it, so a database restart
    # gives a fresh connection instead of an error on the next request.
    # connect_timeout: with the database down, fail in seconds instead of hanging (see main.py).
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency (from Step 4): a session for one request, closed afterwards."""
    with Session(get_engine()) as session:
        yield session
