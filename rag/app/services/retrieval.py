"""Busqueda hibrida sobre pgvector con fusion Reciprocal Rank Fusion.

Por que hibrida y no solo vectorial: en dominio legal la consulta suele traer literales
que el espacio semantico no distingue bien ("art. 245 LCT", "Ley 27.401", "CSJN Fallos
340:1163"). La rama lexica (`tsvector` en espanol) los captura de forma exacta, mientras
la rama vectorial cubre las preguntas parafraseadas. RRF combina ambos rankings sin
necesidad de calibrar scores que estan en escalas distintas.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from cartia_shared import RetrievedChunk, SearchFilters, SearchRequest, SearchResponse
from cartia_shared.embeddings import to_pgvector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.settings import get_settings
from .embeddings import get_embedding_client

logger = logging.getLogger(__name__)


def _build_filters(filters: SearchFilters | None) -> tuple[str, dict[str, Any]]:
    """Devuelve un fragmento SQL de filtros y sus parametros.

    Se inyecta literalmente en ambas ramas en lugar de usar un CTE compartido: un CTE
    referenciado dos veces Postgres lo materializa, y eso le saca el indice HNSW a la
    rama semantica.
    """
    if filters is None:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    def add_in(column: str, values: list[Any] | None, prefix: str) -> None:
        if not values:
            return
        keys = []
        for index, value in enumerate(values):
            key = f"{prefix}_{index}"
            params[key] = str(value)
            keys.append(f":{key}")
        clauses.append(f"{column} IN ({', '.join(keys)})")

    add_in("d.doc_type", filters.doc_types, "dt")
    add_in("d.jurisdiction", filters.jurisdictions, "ju")
    add_in("d.fuero", filters.fueros, "fu")

    if filters.estados:
        keys = []
        for index, value in enumerate(filters.estados):
            key = f"es_{index}"
            params[key] = str(value)
            keys.append(f":{key}")
        # NULL = "sin dato de vigencia" (documentos cargados a mano): pasan siempre.
        clauses.append(f"(d.estado IS NULL OR d.estado IN ({', '.join(keys)}))")

    if filters.document_ids:
        keys = []
        for index, value in enumerate(filters.document_ids):
            key = f"doc_{index}"
            params[key] = str(value)
            keys.append(f"CAST(:{key} AS uuid)")
        clauses.append(f"d.id IN ({', '.join(keys)})")

    if filters.anio_desde is not None:
        params["anio_desde"] = filters.anio_desde
        clauses.append("d.anio >= :anio_desde")

    if filters.anio_hasta is not None:
        params["anio_hasta"] = filters.anio_hasta
        clauses.append("d.anio <= :anio_hasta")

    if not clauses:
        return "", {}
    return " AND " + " AND ".join(clauses), params


_QUERY_TEMPLATE = """
WITH semantic AS (
    SELECT c.id,
           ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector)) AS rnk
    FROM rag_chunks c
    JOIN rag_documents d ON d.id = c.document_id
    WHERE c.embedding IS NOT NULL{filters}
    ORDER BY c.embedding <=> CAST(:qvec AS vector)
    LIMIT :pool
),
lexical AS (
    SELECT c.id,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.tsv, q.query) DESC) AS rnk
    FROM rag_chunks c
    JOIN rag_documents d ON d.id = c.document_id
    CROSS JOIN websearch_to_tsquery('spanish', :qtext) AS q(query)
    WHERE c.tsv @@ q.query{filters}
    ORDER BY ts_rank_cd(c.tsv, q.query) DESC
    LIMIT :pool
),
fused AS (
    SELECT COALESCE(s.id, l.id) AS id,
           :w_sem * COALESCE(1.0 / (:rrf_k + s.rnk), 0.0)
             + (1.0 - :w_sem) * COALESCE(1.0 / (:rrf_k + l.rnk), 0.0) AS score
    FROM semantic s
    FULL OUTER JOIN lexical l ON l.id = s.id
)
SELECT c.id            AS chunk_id,
       c.document_id   AS document_id,
       c.content       AS content,
       c.chunk_index   AS chunk_index,
       c.heading       AS heading,
       c.articulo      AS articulo,
       d.title         AS title,
       d.doc_type      AS doc_type,
       d.jurisdiction  AS jurisdiction,
       d.fuero         AS fuero,
       d.estado        AS estado,
       d.numero        AS numero,
       d.anio          AS anio,
       d.organo        AS organo,
       d.fecha         AS fecha,
       d.citation      AS citation,
       d.source_path   AS source_path,
       f.score         AS score
FROM fused f
JOIN rag_chunks c ON c.id = f.id
JOIN rag_documents d ON d.id = c.document_id
ORDER BY f.score DESC
LIMIT :top_k
"""


async def hybrid_search(session: AsyncSession, request: SearchRequest) -> SearchResponse:
    started = time.perf_counter()
    settings = get_settings()

    query_vector = await get_embedding_client().embed_query(request.query)

    filters_sql, filter_params = _build_filters(request.filters)
    sql = _QUERY_TEMPLATE.format(filters=filters_sql)

    params: dict[str, Any] = {
        "qvec": to_pgvector(query_vector),
        "qtext": request.query,
        "pool": settings.candidate_pool,
        "rrf_k": settings.rrf_k,
        "w_sem": request.semantic_weight,
        "top_k": request.top_k,
        **filter_params,
    }

    # `ef_search` controla el trade-off recall/latencia del HNSW. Se sube por encima del
    # default (40) porque el pool de candidatos se recorta despues con RRF.
    await session.execute(
        text("SET LOCAL hnsw.ef_search = :ef"),
        {"ef": max(64, settings.candidate_pool * 2)},
    )
    rows = (await session.execute(text(sql), params)).mappings().all()

    chunks = [RetrievedChunk.model_validate(dict(row)) for row in rows]
    took_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "hybrid_search query=%r top_k=%s hits=%s took_ms=%s",
        request.query[:120],
        request.top_k,
        len(chunks),
        took_ms,
    )
    return SearchResponse(query=request.query, chunks=chunks, took_ms=took_ms)
