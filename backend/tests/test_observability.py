"""Logs and error reports in production (Week 7 Step 6): JSON lines that carry the interview's
session_id, and Sentry only when a DSN is set, without personal data."""

import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import observability
from app.core.observability import (
    JsonFormatter,
    bind_session,
    bind_session_from_path,
    configure_logging,
    current_session_id,
    init_sentry,
    sentry_options,
)
from app.workers import jobs

logger = logging.getLogger("tests.observability")


@pytest.fixture(autouse=True)
def fresh_logging():
    """configure_logging changes global state: put it back after each test."""
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    uvicorn = {
        n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate)
        for n in observability.TAKEN_OVER_LOGGERS
    }
    yield
    root.handlers[:], root.level = saved
    for name, (handlers, propagate) in uvicorn.items():
        logging.getLogger(name).handlers[:] = handlers
        logging.getLogger(name).propagate = propagate


def record(message: str = "hello", exc_info=None) -> logging.LogRecord:
    return logger.makeRecord(logger.name, logging.WARNING, __file__, 1, message, (), exc_info)


def as_json(rec: logging.LogRecord) -> dict:
    line = JsonFormatter().format(rec)
    assert "\n" not in line  # one event, one line: a traceback must not split it
    return json.loads(line)


# --- The JSON line -----------------------------------------------------------------------------


def test_a_log_line_is_json_with_the_basics():
    line = as_json(record("Session started"))
    assert line["message"] == "Session started"
    assert line["level"] == "warning"
    assert line["logger"] == "tests.observability"
    assert line["time"].endswith("+00:00")  # UTC, so lines from api and worker line up


def test_a_line_outside_an_interview_has_no_session_id():
    assert "session_id" not in as_json(record())


def test_a_line_inside_an_interview_has_its_session_id():
    token = current_session_id.set(42)
    try:
        assert as_json(record())["session_id"] == 42
    finally:
        current_session_id.reset(token)


def test_an_exception_stays_on_the_same_line():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        line = as_json(record("failed", sys.exc_info()))
    assert "ValueError: boom" in line["exception"]


# --- Which interview is this? ------------------------------------------------------------------


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/sessions/{session_id}", dependencies=[Depends(bind_session_from_path)])
    def endpoint(session_id: str) -> dict:
        # A sync endpoint runs in a thread: the id must still be there.
        logger.warning("inside")
        return {"seen": current_session_id.get()}

    return app


def test_a_route_with_a_session_id_tags_its_log_lines(caplog):
    with TestClient(make_app()) as client:
        assert client.get("/sessions/7").json() == {"seen": 7}
    assert [r.session_id for r in caplog.records if r.message == "inside"] == [7]


def test_the_id_does_not_leak_out_of_the_request():
    with TestClient(make_app()) as client:
        client.get("/sessions/7")
    assert current_session_id.get() is None


def test_a_path_that_is_not_a_number_is_left_to_validation():
    with TestClient(make_app()) as client:
        assert client.get("/sessions/abc").json() == {"seen": None}


def test_the_worker_tags_a_report_job_with_its_session(monkeypatch):
    seen = []
    monkeypatch.setattr(
        jobs, "fill_report", lambda db, sid, scorer: seen.append(current_session_id.get())
    )
    monkeypatch.setattr(jobs, "get_engine", lambda: None)
    monkeypatch.setattr(jobs, "Session", _NoDatabase)
    jobs.generate_report(12)
    assert seen == [12]


class _NoDatabase:
    def __init__(self, _engine):
        pass

    def __enter__(self):
        return None

    def __exit__(self, *_):
        return False


def test_bind_session_also_tags_sentry(monkeypatch):
    tags = {}
    monkeypatch.setattr(observability.sentry_sdk, "set_tag", lambda k, v: tags.update({k: v}))
    token = current_session_id.set(None)
    try:
        bind_session(5)
        assert current_session_id.get() == 5
    finally:
        current_session_id.reset(token)
    assert tags == {"session_id": 5}


# --- Setting it up -----------------------------------------------------------------------------


def test_json_logging_takes_over_uvicorns_loggers():
    configure_logging(json_lines=True)
    (handler,) = logging.getLogger().handlers
    assert isinstance(handler.formatter, JsonFormatter)
    for name in observability.TAKEN_OVER_LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate  # so its lines go through the JSON handler


def test_text_logging_leaves_uvicorn_alone():
    before = logging.getLogger("uvicorn.access").handlers[:]
    configure_logging(json_lines=False)
    assert logging.getLogger("uvicorn.access").handlers == before


def test_no_dsn_means_no_sentry(monkeypatch):
    monkeypatch.setattr(observability.sentry_sdk, "init", lambda **_: pytest.fail("init called"))
    init_sentry("", "api")


def test_sentry_gets_no_personal_data():
    options = sentry_options("https://key@example.invalid/1")
    assert options["send_default_pii"] is False  # no IP addresses, cookies or headers
    assert (
        options["include_local_variables"] is False
    )  # no answers or tokens from the code's variables
    assert options["max_request_body_size"] == "never"  # no passwords from login requests
    assert options["traces_sample_rate"] == 0  # errors only: the free plan's quota is for those


def test_sentry_names_the_deployed_commit(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    assert sentry_options("https://key@example.invalid/1")["release"] == "abc123"


def test_the_worker_sets_up_logging_and_sentry_before_listening(monkeypatch):
    from app.workers import main as worker_main

    calls = []
    monkeypatch.setattr(worker_main, "setup_observability", lambda c: calls.append(("setup", c)))

    class FakeWorker:
        def __init__(self, queues, connection):
            calls.append(("queues", queues))

        def work(self):
            calls.append(("work",))

    monkeypatch.setattr(worker_main, "Worker", FakeWorker)
    worker_main.main()
    assert calls == [("setup", "worker"), ("queues", ["reports"]), ("work",)]
