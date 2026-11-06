"""Bring the database up to date before a new version starts: run migrations, then copy in the
interview templates. Railway runs it before each deploy (railway.api.json); it works locally too.

Safe to run any number of times: Alembic skips migrations already applied, and the seed updates
templates instead of duplicating them. If either fails, the deploy stops and the old version keeps
running, so new code never meets an old database.

Run from backend/:
    uv run python -m scripts.prepare_database
"""

from pathlib import Path

from alembic.config import Config

from alembic import command
from scripts.seed_templates import main as seed_templates

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def main() -> None:
    print("Migrations: upgrading to the latest version")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    seed_templates()


if __name__ == "__main__":
    main()
