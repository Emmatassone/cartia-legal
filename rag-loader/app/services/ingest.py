"""Pipeline de ingesta: descubrir -> extraer -> chunkear -> embeddear -> escribir.

Soporta los dos modos que pide el negocio:
  * reindex completo (`reindex=True`): recrea el esquema y vuelve a cargar todo el corpus.
  * ingesta single-document: agrega o actualiza un archivo puntual sin tocar el resto.

La idempotencia se resuelve con `content_hash`: si el archivo no cambio, se saltea. Si
cambio, se borra su fila en `rag_documents` y el ON DELETE CASCADE limpia sus chunks
antes de reinsertar, asi nunca quedan chunks huerfanos de una version anterior.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from cartia_shared import IngestResult
from cartia_shared.embeddings import EmbeddingClient, to_pgvector
from cartia_shared.schema import DROP_SQL, build_ddl
from sqlalchemy import text

from ..core.db import get_engine
from ..core.settings import get_settings
from .chunking import build_embedding_input, chunk_document
from .extract import SUPPORTED_EXTENSIONS, extract_text
from .metadata import infer_metadata

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


def ensure_schema() -> None:
    settings = get_settings()
    with get_engine().begin() as connection:
        connection.execute(text(build_ddl(settings.embedding_dimensions)))
    logger.info("esquema del indice verificado (dim=%s)", settings.embedding_dimensions)


def reset_schema() -> None:
    """Borra y recrea el indice. Solo se usa en el reindex completo."""
    with get_engine().begin() as connection:
        connection.execute(text(DROP_SQL))
    ensure_schema()
    logger.warning("indice vectorial recreado desde cero")


def discover_documents(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTENSIONS else []
    if not root.exists():
        raise FileNotFoundError(f"no existe la ruta: {root}")
    paths = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        # Los sidecars de metadata no son documentos.
        and not path.name.endswith(".meta.json")
        and path.name != "_meta.json"
    ]
    return paths


def resolve_path(raw: str | Path) -> Path:
    """Interpreta la ruta como absoluta, o relativa a `DOCUMENTS_DIR`."""
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    documents_dir = get_settings().documents_dir.expanduser()
    inside = documents_dir / candidate
    return inside if inside.exists() else candidate


def _relative_source_path(path: Path) -> str:
    """Clave estable del documento: ruta relativa a DOCUMENTS_DIR con separador POSIX."""
    documents_dir = get_settings().documents_dir.expanduser().resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(documents_dir).as_posix()
    except ValueError:
        return resolved.as_posix()


def _existing_hash(connection: Any, source_path: str) -> str | None:
    return connection.execute(
        text("SELECT content_hash FROM rag_documents WHERE source_path = :sp"),
        {"sp": source_path},
    ).scalar_one_or_none()


def _write_document(
    connection: Any,
    *,
    document_id: uuid.UUID,
    source_path: str,
    content_hash: str,
    metadata: Any,
    chunks: list[Any],
    vectors: list[list[float]],
) -> None:
    connection.execute(
        text("DELETE FROM rag_documents WHERE source_path = :sp"), {"sp": source_path}
    )
    connection.execute(
        text(
            """
            INSERT INTO rag_documents (
                id, source_path, content_hash, title, doc_type, jurisdiction, fuero,
                estado, organo, numero, anio, fecha, citation, extra, n_chunks
            ) VALUES (
                :id, :source_path, :content_hash, :title, :doc_type, :jurisdiction, :fuero,
                :estado, :organo, :numero, :anio, :fecha, :citation, CAST(:extra AS jsonb),
                :n_chunks
            )
            """
        ),
        {
            "id": str(document_id),
            "source_path": source_path,
            "content_hash": content_hash,
            "title": metadata.title,
            "doc_type": metadata.doc_type.value,
            "jurisdiction": metadata.jurisdiction.value,
            "fuero": metadata.fuero.value if metadata.fuero else None,
            "estado": metadata.estado.value if metadata.estado else None,
            "organo": metadata.organo,
            "numero": metadata.numero,
            "anio": metadata.anio,
            "fecha": metadata.fecha,
            "citation": metadata.citation,
            "extra": json.dumps(metadata.extra),
            "n_chunks": len(chunks),
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO rag_chunks (
                id, document_id, chunk_index, content, heading, articulo, n_chars, embedding
            ) VALUES (
                :id, :document_id, :chunk_index, :content, :heading, :articulo, :n_chars,
                CAST(:embedding AS vector)
            )
            """
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "document_id": str(document_id),
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "heading": chunk.heading,
                "articulo": chunk.articulo,
                "n_chars": len(chunk.content),
                "embedding": to_pgvector(vector),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )


def ingest_paths(
    paths: Iterable[Path],
    *,
    force: bool = False,
    overrides: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> IngestResult:
    started = time.perf_counter()
    settings = get_settings()
    client = EmbeddingClient(
        api_key=settings.google_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    engine = get_engine()

    ingested = skipped = failed = 0
    total_chunks = 0
    errors: list[str] = []

    def report(message: str) -> None:
        logger.info(message)
        if on_progress:
            on_progress(message)

    for path in paths:
        source_path = _relative_source_path(path)
        try:
            body = extract_text(path)
            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

            with engine.connect() as connection:
                previous_hash = _existing_hash(connection, source_path)
            if previous_hash == content_hash and not force:
                skipped += 1
                report(f"sin cambios, se saltea: {source_path}")
                continue

            metadata = infer_metadata(path, body, overrides)
            chunks = chunk_document(
                body,
                max_chars=settings.max_chunk_chars,
                min_chars=settings.min_chunk_chars,
                overlap=settings.chunk_overlap_chars,
            )
            if not chunks:
                raise ValueError("el documento no produjo ningun chunk")

            inputs = [build_embedding_input(chunk, metadata.title) for chunk in chunks]
            vectors = client.embed_documents(inputs)

            with engine.begin() as connection:
                _write_document(
                    connection,
                    document_id=uuid.uuid4(),
                    source_path=source_path,
                    content_hash=content_hash,
                    metadata=metadata,
                    chunks=chunks,
                    vectors=vectors,
                )

            ingested += 1
            total_chunks += len(chunks)
            report(
                f"ingestado: {source_path} "
                f"[{metadata.doc_type.value}/{metadata.jurisdiction.value}] "
                f"{len(chunks)} chunks"
            )
        except Exception as exc:
            failed += 1
            message = f"{source_path}: {exc}"
            errors.append(message)
            logger.exception("falló la ingesta de %s", source_path)
            if on_progress:
                on_progress(f"ERROR {message}")

    return IngestResult(
        documents_ingested=ingested,
        documents_skipped=skipped,
        documents_failed=failed,
        chunks_written=total_chunks,
        took_ms=int((time.perf_counter() - started) * 1000),
        errors=errors,
    )


def run_ingestion(
    target: str | Path | None = None,
    *,
    reindex: bool = False,
    force: bool = False,
    overrides: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> IngestResult:
    settings = get_settings()
    root = resolve_path(target) if target else settings.documents_dir.expanduser()

    if reindex:
        reset_schema()
    else:
        ensure_schema()

    paths = discover_documents(root)
    if not paths:
        return IngestResult(
            documents_ingested=0,
            documents_skipped=0,
            documents_failed=0,
            chunks_written=0,
            took_ms=0,
            errors=[f"no se encontraron documentos soportados en {root}"],
        )

    if on_progress:
        on_progress(f"{len(paths)} documento(s) a procesar desde {root}")
    # Con reindex el esquema esta vacio, asi que el chequeo de hash nunca ahorra trabajo.
    return ingest_paths(paths, force=force or reindex, overrides=overrides, on_progress=on_progress)


def delete_document(source_path: str) -> bool:
    with get_engine().begin() as connection:
        result = connection.execute(
            text("DELETE FROM rag_documents WHERE source_path = :sp"), {"sp": source_path}
        )
    return bool(result.rowcount)
