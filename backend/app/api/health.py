from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check for deployment (Week 7): answers if the server is up."""
    return {"status": "ok"}
