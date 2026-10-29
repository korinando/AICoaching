from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Fixed names for constraints and indexes (e.g. "uq_users_email"). Without this, Postgres
# makes up names, and a later Alembic migration can't reliably find them to drop or change.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",  # all columns: uq_turns_session_id_turn_index
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Parent of every model. Base.metadata is the list of all tables, which Alembic
    compares with the real database to write migrations."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
