from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    google_api_key: str = ""

    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536

    candidate_pool: int = 40
    rrf_k: int = 60

    internal_token: str = "change-me-shared"
    log_level: str = "INFO"

    db_pool_size: int = 5
    db_max_overflow: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
