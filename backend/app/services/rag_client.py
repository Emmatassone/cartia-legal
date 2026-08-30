"""Cliente HTTP del servicio RAG.

El backend nunca consulta la base vectorial directamente: todo el retrieval pasa por el
servicio `rag`, que es el unico dueno del esquema del indice y de la estrategia de
ranking. Asi se puede cambiar de motor de busqueda sin tocar el grafo.
"""

from __future__ import annotations

import logging

import httpx
from cartia_shared import SearchFilters, SearchRequest, SearchResponse

from ..core.settings import get_settings
from .gcp_identity import fetch_id_token

logger = logging.getLogger(__name__)


class RagUnavailableError(RuntimeError):
    pass


async def _headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"X-Internal-Token": settings.internal_token}
    if settings.rag_use_id_token:
        token = await fetch_id_token(settings.rag_service_url.rstrip("/"))
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def search(
    query: str,
    *,
    top_k: int,
    filters: SearchFilters | None = None,
    semantic_weight: float | None = None,
) -> SearchResponse:
    settings = get_settings()
    payload = SearchRequest(
        query=query,
        top_k=top_k,
        filters=filters,
        semantic_weight=(settings.semantic_weight if semantic_weight is None else semantic_weight),
    )
    url = f"{settings.rag_service_url.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload.model_dump(mode="json", exclude_none=True),
                headers=await _headers(),
            )
            response.raise_for_status()
            return SearchResponse.model_validate(response.json())
    except httpx.HTTPStatusError as exc:
        logger.error(
            "el servicio RAG respondio %s: %s", exc.response.status_code, exc.response.text
        )
        raise RagUnavailableError(
            f"el servicio de busqueda respondio {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("no se pudo contactar al servicio RAG en %s: %s", url, exc)
        raise RagUnavailableError("el servicio de busqueda no esta disponible") from exc


async def corpus_stats() -> dict:
    settings = get_settings()
    url = f"{settings.rag_service_url.rstrip('/')}/documents/stats"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=await _headers())
        response.raise_for_status()
        return response.json()
