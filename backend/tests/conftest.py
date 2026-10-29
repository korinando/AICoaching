"""Shared test setup. pytest loads this file automatically; it holds fixtures only, no tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.agent.schemas import InterviewState
from app.agent.templates import new_state
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models import Base

TEST_DB_NAME = "ai_coach_test"


@pytest.fixture
def state() -> InterviewState:
    """A fresh junior_backend interview state for each test.

    Topics: REST APIs, Databases, Git, Debugging, Teamwork (last_topic_index = 4).
    """
    return new_state("junior_backend")


# --- Database (only for tests that ask for `db` or `client`) ----------------------------------


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """A separate ai_coach_test database on the same server, created if missing.

    Never the real database: tests create and delete data freely. scope="session" means
    this runs once for the whole test run, not once per test.
    """
    url = make_url(get_settings().database_url)
    # CREATE DATABASE can't run inside a transaction, hence AUTOCOMMIT, and it must run
    # while connected to another database ("postgres" always exists).
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    engine = create_engine(url.set(database=TEST_DB_NAME))
    # Fresh tables from the current models at the start of every run.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """A session whose changes are all undone after the test, so tests can't affect each other.

    Everything runs inside one outer transaction that is rolled back at the end. The code
    under test can still call commit(): with create_savepoint, that only commits a savepoint
    inside the outer transaction.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """The app, with every endpoint's get_db replaced by the test session above."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
