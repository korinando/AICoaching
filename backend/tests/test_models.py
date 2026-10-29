"""Checks that need no database. Tests against a real (test) database come in Step 10."""

from sqlalchemy import inspect

from app.models import Base, InterviewTemplate
from scripts.seed_templates import template_rows


def test_all_tables_are_registered():
    """A model that isn't imported in app/models/__init__.py is invisible to Alembic."""
    assert set(Base.metadata.tables) == {
        "users",
        "interview_templates",
        "interview_sessions",
        "turns",
    }


def test_seed_rows_match_template_columns():
    """Every value from templates.json must have a column, or seeding fails at runtime."""
    columns = {c.key for c in inspect(InterviewTemplate).columns}
    for values in template_rows().values():
        assert set(values) <= columns


def test_seed_uses_json_keys_as_slugs():
    assert {"junior_backend", "junior_frontend"} <= set(template_rows())
