# One image for the API and the worker (Week 7 Step 1): the same code and libraries, started with a
# different command. docker-compose.yml (or the hosting platform) picks the command.
#
# Two stages: the first has the tools to install the libraries, the second only what runs. The
# tools (uv, pip's cache) never reach the final image, so it's smaller and has less to attack.

# ---- Stage 1: install the Python libraries into /app/.venv ----------------------------------------
FROM python:3.11-slim AS build

RUN pip install --no-cache-dir uv

WORKDIR /app
# Compile .py to bytecode now, so containers don't do it at every start. Copy rather than link files,
# because the cache uv links from stays behind in this stage.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Libraries before code: Docker reuses this slow layer until the lock file changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- Stage 2: what actually runs ------------------------------------------------------------------
FROM python:3.11-slim

# ffmpeg turns browser recordings into one standard format (app/speech/audio.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Not root: if someone breaks into the app, they can't change the system.
RUN useradd --create-home app
WORKDIR /app

# Same path as in stage 1: a virtual environment's programs have their own path written inside them.
COPY --from=build /app/.venv ./.venv
# The code, plus what deploys need: migrations (Step 5) and the template seed script.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Where Whisper models and the Piper voice go. Locally, docker-compose.yml puts my downloaded copies
# here. In the cloud they start empty and the app downloads into them, so `app` must own them.
RUN mkdir whisper_models voices && chown app:app whisper_models voices

USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app PYTHONUNBUFFERED=1

# Models and voices aren't in the image (up to 1.6 GB): mounted from my PC locally, or downloaded on
# first use in the cloud.

EXPOSE 8000
# The API. Hosting platforms often choose the port and pass it as PORT, so it's read at start; sh -c
# is what fills in ${PORT}. `exec` lets uvicorn receive the stop signal directly and shut down cleanly.
# The worker uses this image with: rq worker reports --url ...
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
