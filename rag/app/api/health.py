from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from ..core.db import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "rag"}


@router.get("/health/ready")
async def ready(session: SessionDep) -> dict[str, Any]:
    """Readiness real: la DB responde y el indice vectorial existe."""
    exists = (
        await session.execute(text("SELECT to_regclass('public.rag_chunks') IS NOT NULL"))
    ).scalar_one()
    return {"status": "ok" if exists else "degraded", "index_ready": bool(exists)}
