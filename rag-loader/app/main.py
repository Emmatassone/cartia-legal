"""API on-demand del rag-loader.

Existe para poder disparar una ingesta sin abrir una terminal (desde la UI, un cron o un
Cloud Run Job). Las ingestas corren en background porque un reindex completo excede
cualquier timeout de HTTP razonable; el cliente sigue el avance por `GET /jobs/{id}`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from cartia_shared import IngestRequest, IngestResult
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from .core.db import get_engine
from .core.settings import get_settings
from .services.ingest import delete_document, ensure_schema, run_ingestion

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CartIA Legal - RAG Loader",
    description="Ingesta on-demand de documentos juridicos al indice vectorial.",
    version="0.1.0",
)


def require_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    if not x_internal_token or x_internal_token != get_settings().internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token"
        )


class JobStatus(BaseModel):
    id: uuid.UUID
    state: Literal["running", "succeeded", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    log: list[str] = []
    result: IngestResult | None = None
    error: str | None = None


# Registro en memoria. Alcanza porque el loader es un proceso unico y on-demand; si en
# algun momento corre con replicas habria que moverlo a una tabla.
_JOBS: dict[uuid.UUID, JobStatus] = {}
_MAX_LOG_LINES = 500

router = APIRouter(dependencies=[Depends(require_internal_token)])


def _run_job(job_id: uuid.UUID, payload: IngestRequest) -> None:
    job = _JOBS[job_id]

    def on_progress(message: str) -> None:
        if len(job.log) < _MAX_LOG_LINES:
            job.log.append(message)

    try:
        job.result = run_ingestion(
            payload.path,
            reindex=payload.reindex,
            force=payload.force,
            overrides=dict(payload.metadata),
            on_progress=on_progress,
        )
        job.state = "failed" if job.result.documents_failed else "succeeded"
    except Exception as exc:
        logger.exception("job de ingesta %s fallo", job_id)
        job.state = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = datetime.now(UTC)


@router.post("/ingest", response_model=JobStatus, status_code=status.HTTP_202_ACCEPTED)
def start_ingestion(payload: IngestRequest, background: BackgroundTasks) -> JobStatus:
    job_id = uuid.uuid4()
    job = JobStatus(id=job_id, state="running", started_at=datetime.now(UTC), log=[])
    _JOBS[job_id] = job
    background.add_task(_run_job, job_id, payload)
    return job


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: uuid.UUID) -> JobStatus:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.get("/jobs", response_model=list[JobStatus])
def list_jobs() -> list[JobStatus]:
    return sorted(_JOBS.values(), key=lambda job: job.started_at, reverse=True)


@router.post("/init-schema")
def init_schema() -> dict[str, str]:
    ensure_schema()
    return {"status": "ok"}


@router.delete("/documents")
def remove_document(source_path: str) -> dict[str, Any]:
    deleted = delete_document(source_path)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not indexed")
    return {"deleted": source_path}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rag-loader"}


@app.get("/health/ready")
def ready() -> dict[str, Any]:
    with get_engine().connect() as connection:
        indexed = connection.execute(
            text("SELECT to_regclass('public.rag_documents') IS NOT NULL")
        ).scalar_one()
    return {"status": "ok", "schema_ready": bool(indexed)}


app.include_router(router)
