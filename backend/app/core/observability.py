"""Seeing what the app does in production (Week 7 Step 6).

- Logs: in production, every line is one JSON object, and lines written while working on an
  interview carry its session_id. On Railway you can then filter the logs to one interview.
- Errors: when SENTRY_DSN is set, crashes and logger.exception() calls go to Sentry, tagged with
  the same session_id. Without it (development, tests), nothing is sent anywhere.
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import sentry_sdk
from fastapi import Request

# The interview the current code is working on. A ContextVar and not a global variable: each
# request, WebSocket and thread started from them has its own copy, so two interviews running
# at the same time never see each other's id.
current_session_id: ContextVar[int | None] = ContextVar("current_session_id", default=None)

# Loggers that set up their own output: in JSON mode they send their lines to ours instead.
TAKEN_OVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def bind_session(session_id: int) -> None:
    """From here on, in this request, WebSocket or job: logs and errors belong to this interview."""
    current_session_id.set(session_id)
    sentry_sdk.set_tag("session_id", session_id)


async def bind_session_from_path(request: Request) -> None:
    """A dependency for the /sessions/{session_id}/... routes.

    async on purpose: FastAPI runs a plain `def` dependency in a thread, and a ContextVar set
    there would be lost when the thread finishes. An async one runs in the request itself, and
    the endpoint (even a `def` one, in its thread) starts with a copy that includes the id.
    """
    session_id = request.path_params.get("session_id", "")
    if session_id.isdigit():  # anything else gets FastAPI's usual 422 from the endpoint
        bind_session(int(session_id))


# Every log record gets the current session_id when it's created, so it's right even if a
# handler formats it later (and tests can read it from caplog).
_make_record = logging.getLogRecordFactory()


def _record_with_session_id(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _make_record(*args, **kwargs)
    record.session_id = current_session_id.get()
    return record


logging.setLogRecordFactory(_record_with_session_id)


class JsonFormatter(logging.Formatter):
    """One line per event: {"time", "level", "logger", "message", "session_id"?, "exception"?}.
    Railway reads "level" and "message", and lets you filter on any other field."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if getattr(record, "session_id", None) is not None:
            line["session_id"] = record.session_id
        if record.exc_info:
            # json.dumps turns the traceback's newlines into \n: the whole error stays one line.
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """For development: readable lines, with the session id when there is one."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s%(session)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        session_id = getattr(record, "session_id", None)
        record.session = f" [session {session_id}]" if session_id is not None else ""
        return super().format(record)


def configure_logging(json_lines: bool) -> None:
    """All app logs to stdout, from INFO up (Railway shows stdout as the service's logs)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_lines else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    if json_lines:
        # Uvicorn prints its own lines its own way. In production they must be JSON too, or
        # Railway would show a mix of formats. In development its coloured output stays.
        for name in TAKEN_OVER_LOGGERS:
            logging.getLogger(name).handlers.clear()
            logging.getLogger(name).propagate = True


def sentry_options(dsn: str) -> dict[str, Any]:
    return {
        "dsn": dsn,
        # No IP addresses, cookies or request headers (the login token travels in one).
        "send_default_pii": False,
        # Sentry would otherwise copy the variables of every function in the traceback, and
        # those hold candidates' answers, transcripts and tokens.
        "include_local_variables": False,
        # Never the body of a request: the login form holds a password.
        "max_request_body_size": "never",
        # Errors only. Performance tracing would use up the free plan's quota for little gain.
        "traces_sample_rate": 0,
        # Which deploy an error came from: Railway sets this to the commit it built.
        "release": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
    }


def init_sentry(dsn: str, component: str) -> None:
    """component ("api" or "worker") is a tag, so you can see which service failed."""
    if not dsn:
        return
    sentry_sdk.init(**sentry_options(dsn))
    sentry_sdk.get_global_scope().set_tag("component", component)


def setup_observability(component: str) -> None:
    """Called once when the api or the worker starts."""
    from app.core.config import get_settings  # here, so this module imports without settings

    settings = get_settings()
    configure_logging(json_lines=settings.log_json)
    init_sentry(settings.sentry_dsn.get_secret_value(), component)
