from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB
from app.api.schemas import TemplateOut
from app.models import InterviewTemplate

router = APIRouter(tags=["templates"])


@router.get("/templates")
def list_templates(db: DB) -> list[TemplateOut]:
    """The interview types to choose from on the dashboard.

    No login needed: it's the same public list for everyone and contains nothing private.
    """
    rows = db.scalars(select(InterviewTemplate).order_by(InterviewTemplate.id))
    return [TemplateOut.model_validate(row) for row in rows]
