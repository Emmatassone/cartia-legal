from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    google_api_key: str = ""

    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    embed_batch_size: int = 32

    documents_dir: Path = Path("./documents")

    max_chunk_chars: int = 1800
    min_chunk_chars: int = 250
    chunk_overlap_chars: int = 200

    internal_token: str = "change-me-shared"
    log_level: str = "INFO"

    # Scraper de normas (InfoLEG / datos.jus.gob.ar).
    scraper_dataset_page: str = (
        "https://datos.jus.gob.ar/dataset/base-de-datos-legislativos-infoleg"
    )
    # Si se conoce la URL directa del zip del catalogo, se usa y se saltea el discovery.
    scraper_catalog_url: str = ""
    scraper_delay_seconds: float = 0.8
    scraper_timeout_seconds: float = 60.0
    scraper_user_agent: str = "cartia-legal/0.1 (scraper de normas oficiales)"
    # Donde se guardan el catalogo CSV, la cache de HTML y el manifiesto.
    catalog_dir: Path | None = None

    @property
    def resolved_catalog_dir(self) -> Path:
        return self.catalog_dir or self.documents_dir / "_catalogo"


@lru_cache
def get_settings() -> Settings:
    return Settings()
