"""Shared test setup. pytest loads this file automatically; it holds fixtures only, no tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.agent.interviewer import Interviewer
from app.agent.schemas import InterviewState
from app.agent.templates import new_state
from app.api.deps import get_interviewer
from app.core.db import get_db
from app.core.security import create_token
from app.main import app
from app.models import Base, InterviewTemplate, User
from tests.audio_samples import make_samples
from tests.db_utils import scratch_database_url
from tests.fakes import FakeLLMClient

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
    engine = create_engine(scratch_database_url(TEST_DB_NAME))
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


@pytest.fixture(scope="session")
def audio_samples(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """Real audio files (webm, mp4, ogg, short_webm), generated once per test run.

    Needs ffmpeg: without it the audio tests fail with a clear message instead of
    silently skipping.
    """
    try:
        return make_samples(tmp_path_factory.mktemp("audio"))
    except RuntimeError as e:
        pytest.fail(str(e))


@pytest.fixture
def user(db: Session) -> User:
    """A user row. password_hash is a placeholder: these tests never log in with it."""
    user = User(email="candidate@example.com", password_hash="not-a-real-hash", name="Cand")
    db.add(user)
    db.flush()  # send the INSERT now so user.id is set, without committing
    return user


@pytest.fixture
def template(db: Session) -> InterviewTemplate:
    """Same topics as the `state` fixture: REST APIs, Databases, Git, Debugging, Teamwork."""
    template = InterviewTemplate(
        slug="junior_backend",
        role="Junior Backend Developer",
        level="junior",
        interview_type="technical",
        topics=["REST APIs", "Databases", "Git", "Debugging", "Teamwork"],
        max_main_questions=5,
        max_follow_ups=2,
    )
    db.add(template)
    db.flush()
    return template


@pytest.fixture
def auth_headers(user: User) -> dict[str, str]:
    """Logged in as `user`, without going through /auth/login (and its slow Argon2 hash)."""
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


@pytest.fixture
def fake_llm(client: TestClient) -> FakeLLMClient:
    """Every endpoint's interviewer uses this fake instead of Gemini.

    Starts with an empty script: add decisions in the test with fake_llm.script.extend(...).
    Depends on `client`, so its override is cleared together with get_db's after the test.
    """
    fake = FakeLLMClient([])
    app.dependency_overrides[get_interviewer] = lambda: Interviewer(fake)
    return fake


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """The app, with every endpoint's get_db replaced by the test session above."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
