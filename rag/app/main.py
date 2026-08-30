import logging

from fastapi import FastAPI

from .api.documents import router as documents_router
from .api.health import router as health_router
from .api.search import router as search_router
from .core.settings import get_settings

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="CartIA Legal - RAG",
    description="Retrieval hibrido (vectorial + lexico) sobre el corpus juridico argentino.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(search_router)
app.include_router(documents_router)
