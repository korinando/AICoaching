"""Shared test setup. pytest loads this file automatically; it holds fixtures only, no tests."""

import pytest

from app.agent.schemas import InterviewState
from app.agent.templates import new_state


@pytest.fixture
def state() -> InterviewState:
    """A fresh junior_backend interview state for each test.

    Topics: REST APIs, Databases, Git, Debugging, Teamwork (last_topic_index = 4).
    """
    return new_state("junior_backend")
