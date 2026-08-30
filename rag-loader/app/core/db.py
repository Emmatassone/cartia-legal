from functools import lru_cache

from sqlalchemy import Engine, create_engine

from .settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Engine sincronico: la ingesta es un proceso batch, no necesita concurrencia async."""
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
