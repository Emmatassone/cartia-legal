from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import NormaEstado
from .rag import SearchFilters


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    filters: SearchFilters | None = None


class Citation(BaseModel):
    """Fuente citada en la respuesta. `marker` es el número que aparece en el texto."""

    marker: int
    document_id: UUID
    chunk_id: UUID
    title: str
    citation: str | None = None
    articulo: str | None = None
    estado: NormaEstado | None = None
    snippet: str
    score: float


class StreamStage(StrEnum):
    """Etapas del grafo que la UI muestra mientras se genera la respuesta."""

    GUARDRAILS = "guardrails"
    REWRITE = "rewrite"
    RETRIEVE = "retrieve"
    GRADE = "grade"
    GENERATE = "generate"


class StreamEvent(BaseModel):
    """Evento SSE emitido por `POST /chat`. Un `type` por línea `data:`."""

    type: Literal["stage", "token", "citations", "rejected", "done", "error"]
    stage: StreamStage | None = None
    text: str | None = None
    citations: list[Citation] | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    reason: str | None = None
    meta: dict[str, Any] | None = None
