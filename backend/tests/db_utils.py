"""Creating throwaway test databases on the same Postgres server as the real one."""

from sqlalchemy import URL, create_engine, make_url, text

from app.core.config import get_settings


# Not named test_...: pytest would collect it as a test in every file that imports it.
def scratch_database_url(name: str, *, fresh: bool = False) -> URL:
    """URL of database `name`, created if missing; fresh=True drops and recreates it first.

    Uses the real DATABASE_URL's server and user, never the real database itself.
    """
    url = make_url(get_settings().database_url)
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT, and must run
    # while connected to another database ("postgres" always exists).
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if fresh:
            # FORCE closes leftover connections from an earlier run (Postgres 13+).
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return url.set(database=name)
