"""The job queue: the API puts work in Redis, and the worker in Docker picks it up (Week 5).

Slow work like scoring a whole interview can't happen inside a request: the page would wait, and
a failure or a restart would lose it. In a queue, the job stays in Redis until a worker runs it.
"""

from functools import lru_cache

from redis import Redis
from rq import Queue

from app.core.config import get_settings

QUEUE_NAME = "reports"  # the same name as in docker-compose.yml's worker command


@lru_cache
def get_queue() -> Queue:
    """One queue for the whole server. Creating it doesn't connect: that happens on first use."""
    # socket timeouts: with Redis down, ending an interview must not hang on the queue.
    redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=5)
    return Queue(QUEUE_NAME, connection=redis)
