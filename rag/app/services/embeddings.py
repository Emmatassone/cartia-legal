from functools import lru_cache

from cartia_shared.embeddings import EmbeddingClient

from ..core.settings import get_settings


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    s = get_settings()
    return EmbeddingClient(
        api_key=s.google_api_key,
        model=s.embedding_model,
        dimensions=s.embedding_dimensions,
    )
