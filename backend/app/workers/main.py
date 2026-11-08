"""Starts the worker: python -m app.workers.main

What `rq worker reports` did, plus the production logs and Sentry (Week 7 Step 6). They're set up
here, before the first job: each job runs in a copy of this process (a fork), which inherits them.
rq also sees that our log handler exists and sends its own lines through it, as JSON.
"""

from redis import Redis
from rq import Worker

from app.core.config import get_settings
from app.core.observability import setup_observability
from app.workers.queue import QUEUE_NAME


def main() -> None:
    setup_observability("worker")
    # No socket timeout, unlike the api's connection in queue.py: the worker waits on Redis
    # for the next job, and a timeout would cut that wait off.
    connection = Redis.from_url(get_settings().redis_url)
    Worker([QUEUE_NAME], connection=connection).work()


if __name__ == "__main__":
    main()
