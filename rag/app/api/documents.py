from typing import Annotated, Any

from cartia_shared import DocumentSummary
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from ..core.db import SessionDep
from ..core.deps import require_internal_token

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_internal_token)],
)

_COLUMNS = """
    id, title, doc_type, jurisdiction, fuero, estado, numero, anio,
    citation, source_path, n_chunks, ingested_at
"""


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: str | None = None,
) -> list[Any]:
    """Listado del corpus indexado. La UI lo usa para mostrar qué hay cargado."""
    where = "WHERE title ILIKE :pattern" if q else ""
    sql = f"SELECT {_COLUMNS} FROM rag_documents {where} ORDER BY ingested_at DESC LIMIT :limit OFFSET :offset"  # noqa: E501
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        params["pattern"] = f"%{q}%"
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/stats")
async def corpus_stats(session: SessionDep) -> dict[str, Any]:
    totals = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    (SELECT count(*) FROM rag_documents) AS documents,
                    (SELECT count(*) FROM rag_chunks)    AS chunks,
                    (SELECT count(*) FROM rag_chunks WHERE embedding IS NULL)
                        AS chunks_sin_embedding
                """
                )
            )
        )
        .mappings()
        .one()
    )

    by_type = (
        (
            await session.execute(
                text(
                    "SELECT doc_type, count(*) AS n FROM rag_documents "
                    "GROUP BY doc_type ORDER BY n DESC"
                )
            )
        )
        .mappings()
        .all()
    )

    by_jurisdiction = (
        (
            await session.execute(
                text(
                    "SELECT jurisdiction, count(*) AS n FROM rag_documents "
                    "GROUP BY jurisdiction ORDER BY n DESC"
                )
            )
        )
        .mappings()
        .all()
    )

    by_estado = (
        (
            await session.execute(
                text(
                    "SELECT coalesce(estado, 'sin_dato') AS estado, count(*) AS n "
                    "FROM rag_documents GROUP BY estado ORDER BY n DESC"
                )
            )
        )
        .mappings()
        .all()
    )

    return {
        **dict(totals),
        "by_doc_type": {row["doc_type"]: row["n"] for row in by_type},
        "by_jurisdiction": {row["jurisdiction"]: row["n"] for row in by_jurisdiction},
        "by_estado": {row["estado"]: row["n"] for row in by_estado},
    }


@router.get("/{document_id}", response_model=DocumentSummary)
async def get_document(document_id: str, session: SessionDep) -> Any:
    row = (
        (
            await session.execute(
                text(f"SELECT {_COLUMNS} FROM rag_documents WHERE id = CAST(:id AS uuid)"),
                {"id": document_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return dict(row)
