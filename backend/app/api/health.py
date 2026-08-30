from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from ..core.db import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@router.get("/health/ready")
def ready(session: SessionDep) -> dict[str, Any]:
    try:
        session.exec(text("SELECT 1"))  # type: ignore[call-overload]
        database_ok = True
    except Exception:
        database_ok = False
    return {"status": "ok" if database_ok else "degraded", "database": database_ok}
