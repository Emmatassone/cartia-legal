from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30

    google_api_key: str = ""
    gemini_guardrail_model: str = "gemini-2.5-flash-lite"
    gemini_rewrite_model: str = "gemini-2.5-flash"
    gemini_answer_model: str = "gemini-2.5-pro"
    gemini_transcribe_model: str = "gemini-2.5-flash"

    rag_service_url: str = "http://localhost:8002"
    internal_token: str = "change-me-shared"
    # En Cloud Run el servicio RAG es privado y exige un ID token del metadata server.
    # En local queda apagado porque no hay metadata server.
    rag_use_id_token: bool = False

    retrieval_top_k: int = 8
    retrieval_max_attempts: int = 2
    semantic_weight: float = 0.6
    # Por defecto el retrieval no trae normas derogadas. Los documentos sin dato de
    # vigencia (cargados a mano) no se ven afectados: el filtro los deja pasar.
    retrieval_excluir_derogadas: bool = True

    # Cuantos turnos previos se le pasan al reescritor de consultas.
    history_turns: int = 6

    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    debug: bool = False

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "cartia-legal"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
