"""Copy the interview templates from app/agent/templates.json into the database.

Safe to run again: a template that already exists (same slug) is updated, not duplicated.
Run from backend/ after `uv run alembic upgrade head`:
    uv run python -m scripts.seed_templates
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.templates import load_templates
from app.core.db import get_engine
from app.models import InterviewTemplate


def template_rows() -> dict[str, dict[str, Any]]:
    """templates.json as {slug: column values}. Kept separate so it can be tested without a DB."""
    return {slug: t.model_dump() for slug, t in load_templates().items()}


def seed(db: Session) -> tuple[int, int]:
    """Insert new templates and update existing ones. Returns (added, updated)."""
    added = updated = 0
    for slug, values in template_rows().items():
        row = db.scalar(select(InterviewTemplate).where(InterviewTemplate.slug == slug))
        if row is None:
            db.add(InterviewTemplate(slug=slug, **values))
            added += 1
        else:
            for column, value in values.items():
                setattr(row, column, value)
            updated += 1
    # One commit for everything: if anything fails, nothing is half-saved.
    db.commit()
    return added, updated


def main() -> None:
    with Session(get_engine()) as db:
        added, updated = seed(db)
        total = len(db.scalars(select(InterviewTemplate)).all())
    print(f"Templates: {added} added, {updated} updated, {total} in the database.")


if __name__ == "__main__":
    main()
