# The background worker (Week 5). It runs in Linux because RQ's worker needs fork(), which Windows
# doesn't have. The API still runs directly on the PC for now.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependencies first and the code after: Docker reuses this slow layer until the lock file changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app PYTHONUNBUFFERED=1

# Started by docker-compose.yml, which also gives it the settings.
CMD ["rq", "worker", "reports"]
