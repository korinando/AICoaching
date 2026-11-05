"""add too_short report status

Revision ID: 6cbf03346fbc
Revises: 09b73dacf2de
Create Date: 2026-11-05 14:54:30.648660

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6cbf03346fbc"
down_revision: str | Sequence[str] | None = "09b73dacf2de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema. Alembic can't detect a changed check constraint, so this is written by hand."""
    op.drop_constraint(op.f("ck_feedback_reports_status_valid"), "feedback_reports", type_="check")
    op.create_check_constraint(
        op.f("ck_feedback_reports_status_valid"),
        "feedback_reports",
        "status IN ('pending', 'ready', 'failed', 'too_short')",
    )


def downgrade() -> None:
    """Downgrade schema. A too_short report has no place in the old list, so those rows go first."""
    op.execute("DELETE FROM feedback_reports WHERE status = 'too_short'")
    op.drop_constraint(op.f("ck_feedback_reports_status_valid"), "feedback_reports", type_="check")
    op.create_check_constraint(
        op.f("ck_feedback_reports_status_valid"),
        "feedback_reports",
        "status IN ('pending', 'ready', 'failed')",
    )
