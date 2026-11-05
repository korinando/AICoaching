"""Functions the worker runs. The queue stores only this function's name and its arguments, so the
arguments must be small, simple values, like a session id and not a database object."""


def ping(message: str) -> str:
    """Proves that the worker can run a job and return a result: scripts/check_queue.py."""
    return f"worker got: {message}"
