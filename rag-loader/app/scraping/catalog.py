"""Catalogo oficial de normas: la base InfoLEG publicada en datos.jus.gob.ar.

El portal publica `base-infoleg-normativa-nacional.zip` con un CSV cuyas columnas
estan documentadas en el repo datos-justicia-argentina/Base-de-datos-legislativos-infoleg.
La columna clave es `texto_actualizado`: es la URL directa al texto vigente en InfoLEG,
asi que no hace falta scrapear el buscador para llegar al documento.

El estado de vigencia no viene como columna: se infiere de `observaciones`, que es
donde InfoLEG anota "derogada por..." o "abrogada por...".
"""

from __future__ import annotations

import csv
import io
import logging
import re
import unicodedata
import zipfile
from datetime import date
from pathlib import Path

import httpx
from cartia_shared import NormaEstado
from pydantic import BaseModel

from ..core.settings import get_settings

logger = logging.getLogger(__name__)

CATALOG_ZIP_NAME = "base-infoleg-normativa-nacional.zip"
CATALOG_CSV_NAME = "base-infoleg-normativa-nacional.csv"


class CatalogEntry(BaseModel):
    """Una fila del catalogo. Los tipos quedan como los publica InfoLEG ("Ley",
    "Decreto", ...); la normalizacion a `DocumentType` la hace el pipeline."""

    id_norma: int
    tipo_norma: str
    numero_norma: str = ""
    clase_norma: str | None = None
    organismo_origen: str | None = None
    fecha_sancion: date | None = None
    numero_boletin: int | None = None
    fecha_boletin: date | None = None
    titulo_resumido: str = ""
    titulo_sumario: str | None = None
    texto_resumido: str | None = None
    observaciones: str | None = None
    texto_original: str | None = None
    texto_actualizado: str | None = None
    modificada_por: int | None = None
    modifica_a: int | None = None

    @property
    def estado(self) -> NormaEstado:
        return parse_estado(self.observaciones)

    @property
    def best_url(self) -> str | None:
        """El texto actualizado es el que interesa para un corpus de consulta."""
        return self.texto_actualizado or self.texto_original

    @property
    def numero_normalizado(self) -> str:
        return re.sub(r"[.\s]", "", self.numero_norma)


def _strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn"
    )


def parse_estado(observaciones: str | None) -> NormaEstado:
    """InfoLEG anota la derogacion en observaciones; sin anotacion se asume vigente.

    Esto aplica solo a entradas del catalogo: para documentos cargados a mano la
    metadata deja `estado` en NULL ("sin dato"), que es una afirmacion distinta.
    """
    if not observaciones:
        return NormaEstado.VIGENTE
    texto = _strip_accents(observaciones.lower())
    if re.search(r"parcialmente\s+(?:derogad|abrogad)|(?:derogad|abrogad)\w*\s+parcial", texto):
        return NormaEstado.PARCIALMENTE_VIGENTE
    if re.search(r"\b(?:derogad|abrogad)[ao]\b", texto):
        return NormaEstado.DEROGADA
    return NormaEstado.VIGENTE


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return date.fromisoformat(raw) if fmt == "%Y-%m-%d" else _parse_dmy(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_dmy(raw: str, fmt: str) -> date:
    from datetime import datetime

    return datetime.strptime(raw, fmt).date()


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else None


def find_catalog_url(dataset_page_html: str) -> str:
    """El UUID del recurso cambia con cada actualizacion mensual, asi que la URL del
    zip se descubre del HTML de la pagina del dataset en lugar de hardcodearse."""
    matches = re.findall(
        r'href="([^"]*base-infoleg-normativa-nacional\.zip[^"]*)"', dataset_page_html
    )
    if not matches:
        raise ValueError(
            "no se encontro el link al zip del catalogo en la pagina del dataset; "
            "pasar la URL directa con SCRAPER_CATALOG_URL o --catalog-url"
        )
    url = matches[0].replace("&amp;", "&")
    if url.startswith("/"):
        url = "https://datos.jus.gob.ar" + url
    return url


def download_catalog(catalog_url: str | None = None) -> Path:
    """Baja el zip del catalogo y deja el CSV extraido en `resolved_catalog_dir`."""
    settings = get_settings()
    catalog_dir = settings.resolved_catalog_dir
    catalog_dir.mkdir(parents=True, exist_ok=True)

    url = catalog_url or settings.scraper_catalog_url
    headers = {"User-Agent": settings.scraper_user_agent}
    with httpx.Client(timeout=settings.scraper_timeout_seconds, follow_redirects=True) as client:
        if not url:
            logger.info("descubriendo la URL del catalogo en %s", settings.scraper_dataset_page)
            page = client.get(settings.scraper_dataset_page, headers=headers)
            page.raise_for_status()
            url = find_catalog_url(page.text)
        logger.info("descargando catalogo desde %s", url)
        response = client.get(url, headers=headers)
        response.raise_for_status()

    content = response.content
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("el zip del catalogo no contiene ningun CSV")
            # Si hay varios, el principal es el que no es muestreo ni complementario.
            csv_names.sort(key=lambda name: ("muestreo" in name, "complementaria" in name, name))
            target = catalog_dir / CATALOG_CSV_NAME
            target.write_bytes(archive.read(csv_names[0]))
            logger.info("catalogo extraido: %s (%s)", target, csv_names[0])
            return target

    # Algunas mirrors sirven el CSV directo.
    target = catalog_dir / CATALOG_CSV_NAME
    target.write_bytes(content)
    return target


def load_catalog(path: Path) -> list[CatalogEntry]:
    """Parsea el CSV tolerando los dos encodings con que circulo historicamente."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            # Fuerza un error temprano si el encoding es el equivocado: el header
            # tiene que tener las columnas documentadas.
            header = text.split("\n", 1)[0]
            if "id_norma" not in header or "tipo_norma" not in header:
                continue
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"no se pudo decodificar el catalogo: {path}")

    entries = []
    for row in csv.DictReader(io.StringIO(text)):
        if not (row.get("id_norma") or "").strip():
            continue
        entries.append(
            CatalogEntry(
                id_norma=int(row["id_norma"]),
                tipo_norma=(row.get("tipo_norma") or "").strip(),
                numero_norma=(row.get("numero_norma") or "").strip(),
                clase_norma=(row.get("clase_norma") or "").strip() or None,
                organismo_origen=(row.get("organismo_origen") or "").strip() or None,
                fecha_sancion=_parse_date(row.get("fecha_sancion")),
                numero_boletin=_parse_int(row.get("numero_boletin")),
                fecha_boletin=_parse_date(row.get("fecha_boletin")),
                titulo_resumido=(row.get("titulo_resumido") or "").strip(),
                titulo_sumario=(row.get("titulo_sumario") or "").strip() or None,
                texto_resumido=(row.get("texto_resumido") or "").strip() or None,
                observaciones=(row.get("observaciones") or "").strip() or None,
                texto_original=(row.get("texto_original") or "").strip() or None,
                texto_actualizado=(row.get("texto_actualizado") or "").strip() or None,
                modificada_por=_parse_int(row.get("modificada_por")),
                modifica_a=_parse_int(row.get("modifica_a")),
            )
        )
    logger.info("catalogo cargado: %s normas desde %s", len(entries), path)
    return entries
