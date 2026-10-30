"""The Alembic migrations, run for real on an empty database.

The other tests build their tables straight from the models (Base.metadata.create_all), so
they would still pass if I changed a model and forgot the migration. This test catches
that: the real database is only ever built from migrations.
"""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from app.core.config import get_settings
from app.models import Base
from tests.db_utils import scratch_database_url

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_migrations_build_the_same_schema_as_the_models(monkeypatch):
    url = scratch_database_url("ai_coach_migrations_test", fresh=True)
    # alembic/env.py reads DATABASE_URL from the settings. A real env var wins over .env
    # (Step 2), so this points Alembic at the scratch database instead of the real one.
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_INI))
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "base")  # every migration can be undone...
        command.upgrade(config, "head")  # ...and applied again

        engine = create_engine(url)
        with engine.connect() as conn:
            differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        engine.dispose()
        # Empty = the migrations produce exactly what the models describe.
        # Not empty = a model changed without a migration: run `alembic revision --autogenerate`.
        assert differences == []
    finally:
        get_settings.cache_clear()  # back to the real settings for the other tests
