"""The job queue's setup. scripts/check_queue.py covers the real Redis and worker."""

from app.core.config import get_settings
from app.workers.jobs import ping
from app.workers.queue import QUEUE_NAME, get_queue


def test_ping_returns_its_message():
    assert ping("hello") == "worker got: hello"


def test_queue_uses_the_configured_redis_and_the_workers_queue_name():
    queue = get_queue()

    assert queue.name == QUEUE_NAME
    connection = queue.connection.connection_pool.connection_kwargs
    expected = get_settings().redis_url
    assert f"{connection['host']}:{connection['port']}/{connection['db']}" in expected
