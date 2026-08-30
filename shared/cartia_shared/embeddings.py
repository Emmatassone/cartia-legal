"""Cliente de embeddings compartido por `rag` y `rag-loader`.

Vive en el paquete compartido a proposito: si el modelo, la dimensionalidad, el
`task_type` o la normalizacion difieren entre la ingesta y la consulta, el retrieval
degrada de forma silenciosa (los vectores dejan de ser comparables). Manteniendo una
sola implementacion, ese desfasaje no puede ocurrir.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Literal

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

# Limite conservador: la API acepta mas, pero lotes chicos dan reintentos mas baratos.
_BATCH_SIZE = 32
_MAX_RETRIES = 4


def l2_normalize(vector: list[float]) -> list[float]:
    """Normaliza a norma 1.

    `gemini-embedding-001` solo devuelve vectores normalizados cuando se usa la
    dimensionalidad nativa (3072). Con cualquier `output_dimensionality` menor hay que
    normalizar del lado del cliente para que la distancia coseno sea valida.
    """
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]


class EmbeddingClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimensions: int = 1536,
    ) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY es obligatorio para generar embeddings")
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    def _config(self, task_type: TaskType) -> types.EmbedContentConfig:
        return types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self.dimensions,
        )

    def _unpack(self, response: types.EmbedContentResponse, expected: int) -> list[list[float]]:
        embeddings = response.embeddings or []
        if len(embeddings) != expected:
            raise RuntimeError(
                f"la API devolvio {len(embeddings)} embeddings para {expected} textos"
            )
        return [l2_normalize(list(item.values or [])) for item in embeddings]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Version sincronica, usada por el pipeline de ingesta."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            vectors.extend(self._embed_batch_sync(batch, "RETRIEVAL_DOCUMENT"))
        return vectors

    def _embed_batch_sync(self, batch: list[str], task_type: TaskType) -> list[list[float]]:
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.models.embed_content(
                    model=self.model,
                    contents=batch,  # type: ignore[arg-type]
                    config=self._config(task_type),
                )
                return self._unpack(response, len(batch))
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                backoff = 2**attempt
                logger.warning(
                    "embed_content fallo (intento %s/%s): %s. Reintento en %ss",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
        raise RuntimeError("unreachable")

    async def embed_query(self, text: str) -> list[float]:
        """Version asincronica, usada por el servicio de retrieval en el hot path."""
        vectors = await self._aembed_batch([text], "RETRIEVAL_QUERY")
        return vectors[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            vectors.extend(await self._aembed_batch(batch, "RETRIEVAL_DOCUMENT"))
        return vectors

    async def _aembed_batch(self, batch: list[str], task_type: TaskType) -> list[list[float]]:
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._client.aio.models.embed_content(
                    model=self.model,
                    contents=batch,  # type: ignore[arg-type]
                    config=self._config(task_type),
                )
                return self._unpack(response, len(batch))
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                backoff = 2**attempt
                logger.warning(
                    "embed_content async fallo (intento %s/%s): %s. Reintento en %ss",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
        raise RuntimeError("unreachable")


def to_pgvector(vector: list[float]) -> str:
    """Serializa al literal textual que entiende pgvector: `[0.1,0.2,...]`."""
    return "[" + ",".join(f"{component:.7f}" for component in vector) + "]"
