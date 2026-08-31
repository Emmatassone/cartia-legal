"""Pipeline del scraper: catalogo -> clasificacion -> descarga -> documents/<materia>/.

Escribe dos cosas por norma:
  * `<categoria>/<slug>.txt` con el texto vigente y un encabezado con la ficha de la
    norma (ese encabezado entra al primer chunk y ayuda al embedding y al tsvector).
  * `<categoria>/<slug>.meta.json`, el sidecar que la ingesta ya sabe leer, con toda
    la metadata del catalogo oficial. Asi cada chunk hereda norma, tipo, jurisdiccion,
    materia y estado sin depender de heuristicas sobre el texto.

La idempotencia la da el manifiesto (`_catalogo/manifest.json`): una corrida nueva
saltea lo ya descargado salvo `--force`, y nunca pisa un archivo que el usuario haya
editado a mano sin avisar en el reporte.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cartia_shared import DocumentType, Jurisdiction, NormaEstado
from pydantic import BaseModel, Field

from ..core.settings import get_settings
from .catalog import CatalogEntry, download_catalog, load_catalog
from .classifier import CATEGORIA_FUERO, Categoria, classify
from .fetcher import NormaFetcher

logger = logging.getLogger(__name__)

# Tipos que tienen sentido para un corpus de consulta. El catalogo tambien trae
# comunicaciones, circulares y actos internos que no aportan al RAG.
TIPOS_DEFAULT = {"ley", "decreto", "decreto ley", "decreto de necesidad y urgencia"}

_TIPO_A_DOC_TYPE: dict[str, DocumentType] = {
    "ley": DocumentType.LEY,
    "decreto": DocumentType.DECRETO,
    "decreto ley": DocumentType.DECRETO,
    "decreto de necesidad y urgencia": DocumentType.DECRETO,
    "resolucion": DocumentType.RESOLUCION,
    "resolucion conjunta": DocumentType.RESOLUCION,
    "disposicion": DocumentType.RESOLUCION,
    "acordada": DocumentType.RESOLUCION,
    "decision administrativa": DocumentType.DECRETO,
    "constitucion nacional": DocumentType.CONSTITUCION,
}

_TIPO_LABEL: dict[str, str] = {
    "ley": "Ley",
    "decreto": "Decreto",
    "decreto ley": "Decreto-Ley",
    "decreto de necesidad y urgencia": "DNU",
    "resolucion": "Resolucion",
    "disposicion": "Disposicion",
    "acordada": "Acordada",
    "decision administrativa": "Decision Administrativa",
    "constitucion nacional": "Constitucion Nacional",
}


class ScrapeReport(BaseModel):
    catalogo_total: int = 0
    seleccionadas: int = 0
    descargadas: int = 0
    salteadas: int = 0
    fallidas: int = 0
    sin_texto: int = 0
    por_categoria: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


def _normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    ).strip()


def _slugify(value: str, max_chars: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize(value)).strip("-")
    return slug[:max_chars].strip("-")


def _format_numero(numero: str) -> str:
    """20744 -> 20.744, como se cita en la practica."""
    if not numero.isdigit() or len(numero) < 5:
        return numero
    grupos = []
    resto = numero
    while len(resto) > 3:
        grupos.append(resto[-3:])
        resto = resto[:-3]
    grupos.append(resto)
    return ".".join(reversed(grupos))


def _tipo_normalizado(entry: CatalogEntry) -> str:
    return _normalize(entry.tipo_norma)


def _nombre_archivo(entry: CatalogEntry) -> str:
    """Nombre del .txt dentro de la carpeta de la materia.

    Los numeros puramente digitales conservan el esquema original (compatibilidad con
    lo ya descargado y su manifiesto). Numeros como "S/N" o "1234/95" se slugifican y
    llevan el id de InfoLEG de sufijo: el crudo rompe el path ('/' es separador) y
    hay muchas "Ley S/N" distintas que colisionarian entre si.
    """
    label = _TIPO_LABEL.get(_tipo_normalizado(entry), "norma")
    numero = entry.numero_normalizado
    if numero.isdigit():
        base = f"{_slugify(label)}-{numero}"
    else:
        numero_slug = _slugify(numero)
        sufijo = f"{numero_slug}-id{entry.id_norma}" if numero_slug else f"id{entry.id_norma}"
        base = f"{_slugify(label)}-{sufijo}"
    if entry.titulo_resumido:
        base += f"-{_slugify(entry.titulo_resumido)}"
    return base


def _resolver_nombres(seleccion: list[tuple[CatalogEntry, Categoria]]) -> dict[int, str]:
    """Nombre de archivo por id_norma, desambiguando colisiones.

    El numero se repite entre anos (hay un "Decreto 7" por presidencia) y el slug no
    incluye el ano, asi que normas distintas pueden mapear al mismo path. Cuando eso
    pasa, TODAS las del grupo llevan el id de sufijo: si solo se renombrara la segunda,
    el archivo ya escrito seguiria teniendo el encabezado de una norma y el texto de
    otra.
    """
    conteo = Counter((categoria.value, _nombre_archivo(entry)) for entry, categoria in seleccion)
    nombres: dict[int, str] = {}
    for entry, categoria in seleccion:
        nombre = _nombre_archivo(entry)
        if conteo[(categoria.value, nombre)] > 1:
            nombre = f"{nombre}-id{entry.id_norma}"
        nombres[entry.id_norma] = nombre
    return nombres


def build_sidecar(entry: CatalogEntry, categoria: Categoria) -> dict[str, Any]:
    """Metadata en el formato exacto que espera `infer_metadata` (sidecar .meta.json)."""
    tipo = _tipo_normalizado(entry)
    label = _TIPO_LABEL.get(tipo, entry.tipo_norma)
    numero = entry.numero_normalizado
    numero_legible = _format_numero(numero)
    titulo = entry.titulo_resumido or entry.titulo_sumario or f"{label} {numero_legible}"

    nombre_norma = f"{label} {numero_legible}" if numero else label
    return {
        "title": f"{nombre_norma} - {titulo}" if titulo not in nombre_norma else titulo,
        "doc_type": _TIPO_A_DOC_TYPE.get(tipo, DocumentType.OTRO).value,
        "jurisdiction": Jurisdiction.NACIONAL.value,
        "fuero": CATEGORIA_FUERO[categoria].value,
        "organo": entry.organismo_origen,
        "numero": numero or None,
        "anio": entry.fecha_sancion.year if entry.fecha_sancion else None,
        "fecha": entry.fecha_sancion.isoformat() if entry.fecha_sancion else None,
        "citation": (
            f"{nombre_norma} - {entry.fecha_sancion.isoformat()}"
            if entry.fecha_sancion
            else nombre_norma
        ),
        "estado": entry.estado.value,
        "extra": {
            "infoleg_id": entry.id_norma,
            "materia": categoria.value,
            "url_texto": entry.best_url,
            "boletin": entry.numero_boletin,
            "fecha_boletin": entry.fecha_boletin.isoformat() if entry.fecha_boletin else None,
            "modificada_por": entry.modificada_por,
            "observaciones": entry.observaciones,
        },
    }


def _header_textual(entry: CatalogEntry, categoria: Categoria, sidecar: dict[str, Any]) -> str:
    lineas = [
        sidecar["title"].upper(),
        f"Materia: {categoria.value} | Estado: {entry.estado.value} | Jurisdiccion: nacional",
    ]
    if entry.organismo_origen:
        lineas.append(f"Organismo: {entry.organismo_origen}")
    if entry.fecha_sancion:
        boletin = f" | Boletin Oficial N° {entry.numero_boletin}" if entry.numero_boletin else ""
        lineas.append(f"Sancion: {entry.fecha_sancion.isoformat()}{boletin}")
    if entry.observaciones:
        lineas.append(f"Observaciones: {entry.observaciones}")
    lineas.append(f"Fuente: InfoLEG - {entry.best_url}")
    return "\n".join(lineas)


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("manifiesto corrupto, se empieza de cero: %s", path)
    return {}


def select_entries(
    entries: list[CatalogEntry],
    *,
    materias: set[str] | None = None,
    tipos: set[str] | None = None,
    anio_desde: int | None = None,
    solo_vigentes: bool = False,
    incluir_ruido: bool = False,
) -> list[tuple[CatalogEntry, Categoria]]:
    """Filtra el catalogo. El `ruido` (actos individuales: designaciones, homenajes,
    decretos secretos de personal) se saltea salvo pedido expreso: ocupa un tercio
    del catalogo y no aporta nada a un corpus de consulta juridica."""
    tipos = {_normalize(tipo) for tipo in (tipos or TIPOS_DEFAULT)}
    seleccion = []
    for entry in entries:
        if _tipo_normalizado(entry) not in tipos:
            continue
        if anio_desde and (not entry.fecha_sancion or entry.fecha_sancion.year < anio_desde):
            continue
        if solo_vigentes and entry.estado == NormaEstado.DEROGADA:
            continue
        categoria = classify(entry)
        if categoria == Categoria.RUIDO and not (
            incluir_ruido or (materias and "ruido" in materias)
        ):
            continue
        if materias and categoria.value not in materias:
            continue
        seleccion.append((entry, categoria))
    # Determinismo: mismo catalogo -> mismo orden -> mismo manifiesto.
    seleccion.sort(key=lambda item: item[0].id_norma)
    return seleccion


def scrape(
    *,
    materias: set[str] | None = None,
    tipos: set[str] | None = None,
    limit: int | None = None,
    anio_desde: int | None = None,
    solo_vigentes: bool = False,
    incluir_ruido: bool = False,
    force: bool = False,
    dry_run: bool = False,
    catalog_path: Path | None = None,
    catalog_url: str | None = None,
    on_progress: Any = None,
) -> ScrapeReport:
    settings = get_settings()
    documents_dir = settings.documents_dir.expanduser()
    catalog_dir = settings.resolved_catalog_dir

    def report(message: str) -> None:
        logger.info(message)
        if on_progress:
            on_progress(message)

    if catalog_path is None:
        catalog_path = catalog_dir / "base-infoleg-normativa-nacional.csv"
        if not catalog_path.is_file():
            report("descargando catalogo oficial...")
            catalog_path = download_catalog(catalog_url)
    entries = load_catalog(catalog_path)

    seleccion = select_entries(
        entries,
        materias=materias,
        tipos=tipos,
        anio_desde=anio_desde,
        solo_vigentes=solo_vigentes,
        incluir_ruido=incluir_ruido,
    )
    if limit:
        seleccion = seleccion[:limit]

    result = ScrapeReport(catalogo_total=len(entries), seleccionadas=len(seleccion))
    for _, categoria in seleccion:
        result.por_categoria[categoria.value] = result.por_categoria.get(categoria.value, 0) + 1

    if dry_run:
        return result

    manifest_path = catalog_dir / "manifest.json"
    manifest = _load_manifest(manifest_path)
    nombres = _resolver_nombres(seleccion)

    with NormaFetcher() as fetcher:
        for entry, categoria in seleccion:
            key = str(entry.id_norma)
            carpeta = documents_dir / categoria.value
            destino = carpeta / f"{nombres[entry.id_norma]}.txt"

            previo = manifest.get(key)
            if previo and destino.exists() and not force:
                result.salteadas += 1
                continue

            if not entry.best_url:
                result.sin_texto += 1
                result.errors.append(f"{key}: la entrada del catalogo no tiene URL de texto")
                continue

            # Una norma rota (HTTP, HTML sin texto, nombre de archivo invalido) no
            # puede tirar una corrida de 12 horas: se anota y se sigue.
            try:
                texto = fetcher.fetch_text(entry.best_url, force=force)
                sidecar = build_sidecar(entry, categoria)
                contenido = f"{_header_textual(entry, categoria, sidecar)}\n\n{texto}\n"

                carpeta.mkdir(parents=True, exist_ok=True)
                destino.write_text(contenido, encoding="utf-8")
                destino.with_suffix(".txt.meta.json").write_text(
                    json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as exc:
                result.fallidas += 1
                result.errors.append(f"{key} ({entry.best_url}): {exc}")
                logger.warning("fallo la descarga de la norma %s: %s", key, exc)
                continue

            manifest[key] = {
                "path": destino.relative_to(documents_dir).as_posix(),
                "sha256": hashlib.sha256(contenido.encode("utf-8")).hexdigest(),
                "estado": entry.estado.value,
                "categoria": categoria.value,
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            result.descargadas += 1
            # Checkpoint: en corridas de 12+ horas no se puede perder el manifiesto
            # si el proceso muere a mitad de camino.
            if result.descargadas % 500 == 0:
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            report(f"[{categoria.value}] {sidecar['citation']}")

    # `_meta.json` por carpeta: refuerza el fuero aunque falte algun sidecar puntual.
    for categoria_nombre in result.por_categoria:
        categoria = Categoria(categoria_nombre)
        carpeta = documents_dir / categoria.value
        if carpeta.is_dir():
            (carpeta / "_meta.json").write_text(
                json.dumps(
                    {
                        "jurisdiction": Jurisdiction.NACIONAL.value,
                        "fuero": CATEGORIA_FUERO[categoria].value,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    catalog_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report(
        f"listo: {result.descargadas} descargadas, {result.salteadas} ya estaban, "
        f"{result.fallidas} fallaron"
    )
    return result
