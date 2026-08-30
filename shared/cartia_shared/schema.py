"""Esquema SQL del indice vectorial.

Lo escribe `rag-loader` y lo lee `rag`, asi que el DDL vive en el paquete compartido
para que ambos servicios no puedan divergir en nombres de tabla o de columna.

Las tablas de la aplicacion (usuarios, conversaciones, mensajes) NO estan aca: esas las
maneja Alembic en el backend.
"""

from __future__ import annotations

# `EMBEDDING_DIMENSIONS` se interpola en el DDL, por eso el DDL es un template.
# HNSW en pgvector soporta hasta 2000 dimensiones, de ahi el default de 1536.
DDL_TEMPLATE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS rag_documents (
    id              UUID PRIMARY KEY,
    source_path     TEXT NOT NULL UNIQUE,
    content_hash    TEXT NOT NULL,
    title           TEXT NOT NULL,
    doc_type        TEXT NOT NULL,
    jurisdiction    TEXT NOT NULL,
    fuero           TEXT,
    estado          TEXT,
    organo          TEXT,
    numero          TEXT,
    anio            INTEGER,
    fecha           DATE,
    citation        TEXT,
    extra           JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    n_chunks        INTEGER NOT NULL DEFAULT 0,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Para bases creadas antes de que existiera la columna `estado`.
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS estado TEXT;

CREATE INDEX IF NOT EXISTS rag_documents_hash_idx ON rag_documents (content_hash);
CREATE INDEX IF NOT EXISTS rag_documents_filters_idx
    ON rag_documents (doc_type, jurisdiction, fuero, anio);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id           UUID PRIMARY KEY,
    document_id  UUID NOT NULL REFERENCES rag_documents (id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    heading      TEXT,
    articulo     TEXT,
    n_chars      INTEGER NOT NULL,
    embedding    VECTOR({dimensions}),
    tsv          TSVECTOR GENERATED ALWAYS AS (
                     to_tsvector(
                         'spanish',
                         coalesce(heading, '') || ' ' || coalesce(articulo, '') || ' ' || content
                     )
                 ) STORED,
    UNIQUE (document_id, chunk_index)
);

-- Indice ANN para la rama semantica. `vector_cosine_ops` porque los embeddings
-- se guardan normalizados a norma 1.
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Indice para la rama lexica. Imprescindible en legal: "art. 245 LCT" o "Ley 27.401"
-- son literales que la busqueda semantica sola no matchea de forma confiable.
CREATE INDEX IF NOT EXISTS rag_chunks_tsv_idx ON rag_chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS rag_chunks_document_idx ON rag_chunks (document_id);
"""

DROP_SQL = """
DROP TABLE IF EXISTS rag_chunks;
DROP TABLE IF EXISTS rag_documents;
"""


def build_ddl(dimensions: int) -> str:
    return DDL_TEMPLATE.format(dimensions=dimensions)
