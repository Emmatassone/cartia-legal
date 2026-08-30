from __future__ import annotations

from typing import Any, TypedDict

from cartia_shared import Citation, RetrievedChunk, SearchFilters


class Turn(TypedDict):
    role: str
    content: str


class LegalRAGState(TypedDict, total=False):
    """Estado del grafo. `total=False` porque cada nodo completa solo su parte."""

    # Entrada
    question: str
    history: list[Turn]
    filters: SearchFilters | None

    # Nodo guardrails
    allowed: bool
    rejection_reason: str

    # Nodo rewrite
    search_queries: list[str]

    # Nodo retrieve
    chunks: list[RetrievedChunk]
    attempts: int

    # Nodo grade
    sufficient: bool
    missing: str

    # Nodo generate
    answer: str
    citations: list[Citation]

    # Telemetria que la UI muestra en el panel de detalle
    meta: dict[str, Any]
