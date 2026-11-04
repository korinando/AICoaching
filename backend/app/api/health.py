from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.deps import DB

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check for deployment (Week 7): answers if the server is up.

    It doesn't touch the database: restarting this server wouldn't fix a stopped database.
    """
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: DB) -> dict[str, str]:
    """Can this server really do its work? 503 if the database can't be reached."""
    try:
        db.execute(text("SELECT 1"))
    except OperationalError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable") from None
    return {"status": "ready"}
