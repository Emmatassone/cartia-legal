from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import DocumentType, Fuero, Jurisdiction, NormaEstado


class SearchFilters(BaseModel):
    """Filtros de metadata aplicados antes del ranking, en el motor de búsqueda."""

    doc_types: list[DocumentType] | None = None
    jurisdictions: list[Jurisdiction] | None = None
    fueros: list[Fuero] | None = None
    anio_desde: int | None = None
    anio_hasta: int | None = None
    document_ids: list[UUID] | None = None
    # Los documentos con estado NULL (cargados a mano, sin dato de vigencia) pasan
    # siempre este filtro: excluirlos por precaucion vaciaria el corpus manual.
    estados: list[NormaEstado] | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=50)
    filters: SearchFilters | None = None
    # Peso relativo de la búsqueda vectorial frente a la léxica en la fusión RRF.
    # 1.0 = puramente semántica, 0.0 = puramente por palabras clave.
    semantic_weight: float = Field(default=0.6, ge=0.0, le=1.0)


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    content: str
    score: float
    chunk_index: int
    title: str
    doc_type: DocumentType
    jurisdiction: Jurisdiction
    fuero: Fuero | None = None
    estado: NormaEstado | None = None
    articulo: str | None = None
    heading: str | None = None
    numero: str | None = None
    anio: int | None = None
    organo: str | None = None
    fecha: date | None = None
    citation: str | None = None
    source_path: str | None = None


class SearchResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    took_ms: int


class DocumentSummary(BaseModel):
    id: UUID
    title: str
    doc_type: DocumentType
    jurisdiction: Jurisdiction
    fuero: Fuero | None = None
    estado: NormaEstado | None = None
    numero: str | None = None
    anio: int | None = None
    citation: str | None = None
    source_path: str
    n_chunks: int
    ingested_at: datetime


class IngestRequest(BaseModel):
    """Pedido de ingesta on-demand contra el servicio rag-loader."""

    # Ruta a un archivo o a un directorio, relativa a DOCUMENTS_DIR o absoluta.
    path: str
    # Si es True borra todo el índice antes de ingestar (reindex completo).
    reindex: bool = False
    # Reprocesa aunque el hash del contenido no haya cambiado.
    force: bool = False
    # Overrides de metadata; lo que no se pasa se infiere del documento.
    metadata: dict[str, str | int] = Field(default_factory=dict)


class IngestResult(BaseModel):
    documents_ingested: int
    documents_skipped: int
    documents_failed: int
    chunks_written: int
    took_ms: int
    errors: list[str] = Field(default_factory=list)
