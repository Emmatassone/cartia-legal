"""Inferencia de metadata legal a partir del nombre de archivo y del encabezado.

La metadata es lo que despues permite filtrar el retrieval por jurisdiccion, fuero,
tipo de norma o rango de anios, asi que vale la pena inferirla bien. El orden de
precedencia es: overrides explicitos del usuario > sidecar `.meta.json` >
`_meta.json` del directorio > heuristicas sobre el texto.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from cartia_shared import DocumentType, Fuero, Jurisdiction, NormaEstado
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DocumentMetadata(BaseModel):
    title: str
    doc_type: DocumentType = DocumentType.OTRO
    jurisdiction: Jurisdiction = Jurisdiction.DESCONOCIDA
    fuero: Fuero | None = None
    estado: NormaEstado | None = None
    organo: str | None = None
    numero: str | None = None
    anio: int | None = None
    fecha: date | None = None
    citation: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


_DOC_TYPE_PATTERNS: list[tuple[DocumentType, str]] = [
    (DocumentType.CONSTITUCION, r"\bconstituci[oó]n\b"),
    (DocumentType.CODIGO, r"\bc[oó]digo\b"),
    (DocumentType.LEY, r"\bley(?:es)?\b|\bley\s*n[°ºo]"),
    (DocumentType.DECRETO, r"\bdecreto\b|\bdnu\b"),
    (DocumentType.RESOLUCION, r"\bresoluci[oó]n\b|\bdisposici[oó]n\b"),
    (DocumentType.CONVENIO_COLECTIVO, r"\bconvenio colectivo\b|\bcct\b"),
    (DocumentType.FALLO, r"\bfallo\b|\bsentencia\b|\bcsjn\b|\bc\.s\.j\.n\b|\bs\.c\.\b"),
    (DocumentType.DICTAMEN, r"\bdictamen\b"),
    (DocumentType.DOCTRINA, r"\bdoctrina\b|\bcomentario\b|\bart[ií]culo de\b"),
    (DocumentType.CONTRATO, r"\bcontrato\b|\bconvenio de\b|\bacuerdo de\b"),
    (DocumentType.ESCRITO, r"\bdemanda\b|\bcontestaci[oó]n\b|\brecurso\b|\bapelaci[oó]n\b"),
]

_JURISDICTION_PATTERNS: list[tuple[Jurisdiction, str]] = [
    (Jurisdiction.CABA, r"\bcaba\b|ciudad aut[oó]noma de buenos aires|ciudad de buenos aires"),
    (Jurisdiction.BUENOS_AIRES, r"provincia de buenos aires|\bpba\b|\bscba\b"),
    (Jurisdiction.CORDOBA, r"\bc[oó]rdoba\b"),
    (Jurisdiction.SANTA_FE, r"santa fe"),
    (Jurisdiction.MENDOZA, r"\bmendoza\b"),
    (Jurisdiction.TUCUMAN, r"tucum[aá]n"),
    (Jurisdiction.SALTA, r"\bsalta\b"),
    (Jurisdiction.ENTRE_RIOS, r"entre r[ií]os"),
    (Jurisdiction.NEUQUEN, r"neuqu[eé]n"),
    (Jurisdiction.RIO_NEGRO, r"r[ií]o negro"),
    (Jurisdiction.CHUBUT, r"\bchubut\b"),
    (Jurisdiction.MISIONES, r"\bmisiones\b"),
    (Jurisdiction.CORRIENTES, r"\bcorrientes\b"),
    (Jurisdiction.CHACO, r"\bchaco\b"),
    (Jurisdiction.JUJUY, r"\bjujuy\b"),
    (Jurisdiction.LA_PAMPA, r"la pampa"),
    (Jurisdiction.LA_RIOJA, r"la rioja"),
    (Jurisdiction.SAN_JUAN, r"san juan"),
    (Jurisdiction.SAN_LUIS, r"san luis"),
    (Jurisdiction.SANTA_CRUZ, r"santa cruz"),
    (Jurisdiction.SANTIAGO_DEL_ESTERO, r"santiago del estero"),
    (Jurisdiction.TIERRA_DEL_FUEGO, r"tierra del fuego"),
    (Jurisdiction.CATAMARCA, r"\bcatamarca\b"),
    (Jurisdiction.FORMOSA, r"\bformosa\b"),
    (Jurisdiction.FEDERAL, r"\bfederal\b|c[aá]mara nacional|juzgado nacional"),
    (Jurisdiction.NACIONAL, r"\bnacional\b|bolet[ií]n oficial de la rep[uú]blica argentina"),
]

_FUERO_PATTERNS: list[tuple[Fuero, str]] = [
    (
        Fuero.LABORAL,
        r"\blaboral\b|contrato de trabajo|\blct\b|riesgos del trabajo|\bart\b.*trabajo"
        r"|despido|convenio colectivo",
    ),
    (Fuero.FAMILIA, r"\bfamilia\b|alimentos|divorcio|r[eé]gimen de comunicaci[oó]n|adopci[oó]n"),
    (Fuero.PENAL, r"\bpenal\b|delito|imputad|procesal penal|\bcpp\b"),
    (
        Fuero.TRIBUTARIO,
        r"tributari|impuest|\bafip\b|\barca\b|ganancias|\biva\b|procedimiento fiscal",
    ),
    (Fuero.CONSUMIDOR, r"defensa del consumidor|\bconsumidor\b|relaci[oó]n de consumo"),
    (
        Fuero.SOCIETARIO,
        r"sociedades comerciales|\bsociedad an[oó]nima\b|\bsrl\b|\bsas\b|\bley 19\.?550\b",
    ),  # noqa: E501
    (Fuero.PREVISIONAL, r"previsional|jubilaci[oó]n|\banses\b|\bsipa\b|movilidad jubilatoria"),
    (
        Fuero.ADMINISTRATIVO,
        r"administrativ|procedimientos administrativos|contrataciones del estado",
    ),  # noqa: E501
    (Fuero.CONSTITUCIONAL, r"constitucional|amparo|habeas"),
    (Fuero.AMBIENTAL, r"ambiental|\bambiente\b|bosques nativos|glaciares"),
    (Fuero.DATOS_PERSONALES, r"datos personales|\bley 25\.?326\b|privacidad"),
    (
        Fuero.PROPIEDAD_INTELECTUAL,
        r"propiedad intelectual|marcas y patentes|derecho de autor|\bley 11\.?723\b",
    ),  # noqa: E501
    (Fuero.MIGRATORIO, r"migratori|\bley 25\.?871\b|residencia precaria"),
    (Fuero.COMERCIAL, r"comercial|concursos y quiebras|\bcheque\b|fideicomiso"),
    (Fuero.CIVIL, r"\bcivil\b|c[oó]digo civil y comercial|\bccyc\b|da[nñ]os y perjuicios"),
]

_ORGANO_PATTERNS: list[tuple[str, str]] = [
    ("CSJN", r"corte suprema de justicia de la naci[oó]n|\bcsjn\b"),
    ("SCBA", r"suprema corte de justicia de la provincia de buenos aires|\bscba\b"),
    ("CNAT", r"c[aá]mara nacional de apelaciones del trabajo|\bcnat\b"),
    ("CNCiv", r"c[aá]mara nacional de apelaciones en lo civil"),
    ("CNCom", r"c[aá]mara nacional de apelaciones en lo comercial"),
    ("CNCP", r"c[aá]mara nacional de casaci[oó]n penal"),
    ("CNACAF", r"c[aá]mara nacional de apelaciones en lo contencioso administrativo federal"),
    ("TFN", r"tribunal fiscal de la naci[oó]n"),
    ("PGN", r"procuraci[oó]n general de la naci[oó]n"),
    (
        "Congreso",
        r"honorable congreso de la naci[oó]n|c[aá]mara de diputados|senado de la naci[oó]n",
    ),  # noqa: E501
    ("PEN", r"poder ejecutivo nacional"),
]


def _first_match(patterns: list[tuple[Any, str]], haystack: str) -> Any | None:
    for value, pattern in patterns:
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            return value
    return None


def _infer_numero(haystack: str) -> str | None:
    """Extrae el numero de norma, tolerando "27.401", "27401" y "N° 27.401"."""
    match = re.search(
        r"\b(?:ley|decreto|resoluci[oó]n|disposici[oó]n|dnu)\s*(?:n[°ºo]\.?\s*)?"
        r"(\d{1,3}(?:[.\s]\d{3})*|\d{2,6})",
        haystack,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"[.\s]", "", match.group(1))


def _infer_anio(haystack: str) -> int | None:
    years = [int(year) for year in re.findall(r"\b(1[89]\d{2}|20[0-4]\d)\b", haystack)]
    # El anio de sancion suele ser el ultimo mencionado en el encabezado (fecha de firma).
    return max(years) if years else None


def _infer_fecha(haystack: str) -> date | None:
    meses = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }
    textual = re.search(
        r"\b(\d{1,2})\s+de\s+([a-zá]+)\s+de\s+(\d{4})", haystack, flags=re.IGNORECASE
    )
    if textual:
        month = meses.get(textual.group(2).lower())
        if month:
            try:
                return date(int(textual.group(3)), month, int(textual.group(1)))
            except ValueError:
                pass
    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", haystack)
    if numeric:
        try:
            return date(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
        except ValueError:
            return None
    return None


def _infer_estado(header: str) -> NormaEstado | None:
    """Solo se afirma la derogacion cuando el texto la menciona; nunca se asume vigencia,
    porque un documento cargado a mano sin dato no es lo mismo que uno vigente."""
    if re.search(
        r"parcialmente\s+(?:derogad|abrogad)|(?:derogad|abrogad)\w*\s+parcialmente",
        header,
        flags=re.IGNORECASE,
    ):
        return NormaEstado.PARCIALMENTE_VIGENTE
    if re.search(r"\b(?:derogad|abrogad)[ao]a?\b", header, flags=re.IGNORECASE):
        return NormaEstado.DEROGADA
    return None


def _build_citation(meta: DocumentMetadata) -> str:
    parts: list[str] = []
    if meta.doc_type not in {DocumentType.OTRO, DocumentType.FALLO}:
        label = meta.doc_type.value.replace("_", " ").capitalize()
        parts.append(f"{label} {meta.numero}" if meta.numero else label)
    if meta.doc_type == DocumentType.FALLO and meta.organo:
        parts.append(meta.organo)
    if not parts:
        parts.append(meta.title)
    if meta.fecha:
        parts.append(meta.fecha.isoformat())
    elif meta.anio:
        parts.append(str(meta.anio))
    return " - ".join(parts)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("no se pudo leer %s: %s", path, exc)
        return {}


def _sidecar_metadata(path: Path) -> dict[str, Any]:
    """`_meta.json` del directorio como base, sobrescrito por `<archivo>.meta.json`."""
    merged: dict[str, Any] = {}
    directory_meta = path.parent / "_meta.json"
    if directory_meta.is_file():
        merged.update(_read_json(directory_meta))
    file_meta = path.with_suffix(path.suffix + ".meta.json")
    if file_meta.is_file():
        merged.update(_read_json(file_meta))
    return merged


def _humanize_filename(path: Path) -> str:
    stem = re.sub(r"[_-]+", " ", path.stem).strip()
    return re.sub(r"\s{2,}", " ", stem)


def infer_metadata(
    path: Path,
    text: str,
    overrides: dict[str, Any] | None = None,
) -> DocumentMetadata:
    # Solo el encabezado: mas abajo el cuerpo menciona otras normas y contamina la inferencia.
    header = text[:3000]
    haystack = f"{path.stem.replace('_', ' ')}\n{header}"

    doc_type = _first_match(_DOC_TYPE_PATTERNS, haystack) or DocumentType.OTRO
    jurisdiction = _first_match(_JURISDICTION_PATTERNS, haystack) or Jurisdiction.DESCONOCIDA
    fuero = _first_match(_FUERO_PATTERNS, haystack)
    organo = _first_match(_ORGANO_PATTERNS, haystack)

    inferred: dict[str, Any] = {
        "title": _humanize_filename(path),
        "doc_type": doc_type,
        "jurisdiction": jurisdiction,
        "fuero": fuero,
        "organo": organo,
        "numero": _infer_numero(haystack),
        "anio": _infer_anio(haystack),
        "fecha": _infer_fecha(haystack),
        "estado": _infer_estado(header),
    }

    inferred.update({k: v for k, v in _sidecar_metadata(path).items() if v not in (None, "")})
    inferred.update({k: v for k, v in (overrides or {}).items() if v not in (None, "")})

    metadata = DocumentMetadata.model_validate(inferred)
    if not metadata.citation:
        metadata.citation = _build_citation(metadata)
    return metadata
