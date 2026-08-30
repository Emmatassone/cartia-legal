"""Descarga del texto de las normas desde InfoLEG.

Las URL vienen del catalogo (`texto_actualizado` / `texto_original`) y apuntan a
`servicios.infoleg.gob.ar/infolegInternet/anexos/.../{texact,norma}.htm`. Son paginas
HTML viejas con navegacion alrededor del cuerpo de la norma, asi que el HTML crudo no
se guarda: se extrae el texto, se normaliza con la misma funcion que usa la ingesta y
se persiste como `.txt`. Asi el chunker recibe entrada limpia y el `content_hash` no
cambia si InfoLEG retoca el layout pero no el texto.

La cortesia importa: es un servicio publico, se pide con delay entre requests, un
User-Agent identificable y cache en disco para no repetir descargas entre corridas.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from ..core.settings import get_settings
from ..services.extract import normalize_text

logger = logging.getLogger(__name__)

_TAGS_BASURA = ["script", "style", "nav", "footer", "header", "form", "iframe", "noscript"]
_CLASE_CONTENEDOR = re.compile(r"detalle|norma|content|texto", flags=re.IGNORECASE)


def html_to_text(html: bytes | str) -> str:
    """Extrae el cuerpo de la norma de una pagina de InfoLEG.

    InfoLEG marca el contenido con anchors por articulo; cuando existe un contenedor
    principal se prefiere eso, si no se toma el body completo sin la navegacion.

    Recibe bytes: las paginas viejas de InfoLEG son Latin-1 sin header `charset`, y
    decodificarlas como UTF-8 (el default de httpx) destruye los acentos. Con bytes,
    BeautifulSoup detecta el encoding por el <meta> o por el contenido.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_TAGS_BASURA):
        tag.decompose()

    container = (
        soup.find("div", id="content")
        or soup.find("div", class_=_CLASE_CONTENEDOR)
        or soup.body
        or soup
    )
    # Los <br> y <p> son los cortes de linea reales del texto de la norma.
    for br in container.find_all("br"):
        br.replace_with("\n")
    text = container.get_text("\n")
    return normalize_text(text)


class NormaFetcher:
    """Cliente HTTP con rate limiting y cache en disco."""

    def __init__(self, cache_dir: Path | None = None, delay: float | None = None) -> None:
        settings = get_settings()
        self._delay = settings.scraper_delay_seconds if delay is None else delay
        self._cache_dir = cache_dir or settings.resolved_catalog_dir / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            timeout=settings.scraper_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.scraper_user_agent},
        )
        self._last_request_at = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NormaFetcher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _cache_path(self, url: str) -> Path:
        return self._cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:20]}.html"

    def fetch_html(self, url: str, *, force: bool = False) -> bytes:
        cache_path = self._cache_path(url)
        if cache_path.exists() and not force:
            return cache_path.read_bytes()

        # Delay medido desde la ultima request, no sleep fijo: si el proceso estuvo
        # horas clasificando, no hay que esperar antes del primer pedido.
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        response = self._client.get(url)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        # Se cachean los bytes crudos: la decodificacion la hace BeautifulSoup.
        cache_path.write_bytes(response.content)
        return response.content

    def fetch_text(self, url: str, *, force: bool = False) -> str:
        text = html_to_text(self.fetch_html(url, force=force))
        if len(text) < 200:
            raise ValueError(
                f"se extrajeron solo {len(text)} caracteres de {url}; "
                "la pagina probablemente cambio de formato o es un anexo sin texto"
            )
        return text
