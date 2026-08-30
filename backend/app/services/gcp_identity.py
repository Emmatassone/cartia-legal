"""ID tokens del metadata server, para invocar servicios privados de Cloud Run.

El servicio RAG se despliega con `--no-allow-unauthenticated`, asi que ademas del
`X-Internal-Token` de aplicacion hay que presentar un ID token de Google firmado para la
audiencia del servicio destino. En local no hay metadata server, y por eso esto se activa
con `RAG_USE_ID_TOKEN`.

El token se cachea: pedirlo en cada consulta agregaria un round-trip al metadata server
sobre el hot path del chat.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)
# Los ID tokens duran una hora. Se renuevan cinco minutos antes para no usar uno al borde
# del vencimiento en una request que tarde.
_REFRESH_MARGIN_SECONDS = 300
_TOKEN_LIFETIME_SECONDS = 3600

_cache: dict[str, tuple[str, float]] = {}


async def fetch_id_token(audience: str) -> str:
    cached = _cache.get(audience)
    now = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            _METADATA_URL,
            params={"audience": audience, "format": "full"},
            headers={"Metadata-Flavor": "Google"},
        )
        response.raise_for_status()
        token = response.text.strip()

    _cache[audience] = (token, now + _TOKEN_LIFETIME_SECONDS - _REFRESH_MARGIN_SECONDS)
    logger.info("ID token obtenido para la audiencia %s", audience)
    return token
