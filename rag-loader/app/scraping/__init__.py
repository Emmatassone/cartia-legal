"""Scraping de normas argentinas desde fuentes oficiales.

Flujo: catalogo oficial (datos.jus.gob.ar, base InfoLEG) -> clasificacion por materia
-> descarga del texto vigente desde InfoLEG -> escritura en `documents/<materia>/`
con sidecar `.meta.json`, que es exactamente el formato que la ingesta ya entiende.
"""

from .catalog import CatalogEntry, download_catalog, load_catalog, parse_estado
from .classifier import Categoria, classify
from .pipeline import ScrapeReport, scrape

__all__ = [
    "CatalogEntry",
    "Categoria",
    "ScrapeReport",
    "classify",
    "download_catalog",
    "load_catalog",
    "parse_estado",
    "scrape",
]
