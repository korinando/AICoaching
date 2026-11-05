"""Is the job queue working? Sends one job through Redis to the worker in Docker and waits.

Run from backend/, after docker compose up -d --wait:
    uv run python -m scripts.check_queue
"""

import time

from app.workers.jobs import ping
from app.workers.queue import get_queue

TIMEOUT_S = 30


def main() -> None:
    job = get_queue().enqueue(ping, "hello")
    started = time.perf_counter()
    while time.perf_counter() - started < TIMEOUT_S:
        status = job.get_status(refresh=True)
        if status == "finished":
            took = time.perf_counter() - started
            print(f"finished in {took:.2f} s: {job.return_value()!r}")
            return
        if status == "failed":
            raise SystemExit(f"The job failed:\n{job.latest_result().exc_string}")
        time.sleep(0.1)
    raise SystemExit(f"No result after {TIMEOUT_S} s. Is the worker running? docker compose ps")


if __name__ == "__main__":
    main()
