"""Chunking sensible a la estructura de los documentos juridicos argentinos.

En normativa, la unidad semantica natural es el articulo: un abogado pregunta "que dice
el art. 245 de la LCT", no "que dice el caracter 8000 al 9800". Partir por ventanas fijas
corta articulos al medio y hace que el chunk recuperado no alcance para responder.

La estrategia es:
  1. Si el texto tiene estructura de articulos (>= 3 matches), se parte por articulo y se
     arrastra el titulo/capitulo vigente como encabezado del chunk.
  2. Los articulos cortos consecutivos se agrupan hasta `max_chars` (evita miles de chunks
     de una linea, que degradan el ranking).
  3. Los articulos largos se subdividen por parrafo con overlap, repitiendo el numero de
     articulo en cada parte para no perder la referencia.
  4. Si no hay estructura de articulos (fallos, doctrina, contratos), se parte por parrafo
     con overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "ARTICULO 245", "Art. 14 bis", "ARTÍCULO 1° -", "Art 1030 ter"
_ARTICLE_RE = re.compile(
    r"^[ \t]*(?:ART[IÍ]CULO|ARTICULO|ART\.?)\s*"
    r"(\d+(?:\s*[°ºª])?(?:\s*(?:bis|ter|quater|quinquies))?)"
    r"\s*[.\-–:)]?",
    re.MULTILINE | re.IGNORECASE,
)

# Encabezados de agrupamiento que dan contexto jerarquico al articulo.
_HEADING_RE = re.compile(
    r"^[ \t]*((?:LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N|PARTE|ANEXO)\s+[^\n]{0,120})$",
    re.MULTILINE | re.IGNORECASE,
)

_MIN_ARTICLES_FOR_STRUCTURED = 3
# Si el primer articulo aparece dentro de este prefijo, el documento ES una norma (o el
# recorte de un articulo) y no un texto que de paso cita uno.
_ARTICLE_HEAD_WINDOW = 400


@dataclass
class Chunk:
    content: str
    chunk_index: int = 0
    heading: str | None = None
    articulo: str | None = None


@dataclass
class _Segment:
    """Bloque de texto crudo con la referencia estructural que le corresponde."""

    text: str
    heading: str | None = None
    articulo: str | None = None
    parts: list[str] = field(default_factory=list)


def _normalize_article_number(raw: str) -> str:
    number = re.sub(r"\s+", " ", raw).strip().rstrip("°ºª.")
    return re.sub(r"\s+", " ", number)


def _headings_by_position(text: str) -> list[tuple[int, str]]:
    return [
        (match.start(), re.sub(r"\s+", " ", match.group(1)).strip())
        for match in _HEADING_RE.finditer(text)
    ]


def _heading_at(headings: list[tuple[int, str]], position: int) -> str | None:
    current = None
    for start, heading in headings:
        if start <= position:
            current = heading
        else:
            break
    return current


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return paragraphs or ([text.strip()] if text.strip() else [])


def _atomic_units(text: str, limit: int) -> list[str]:
    """Parte en unidades de a lo sumo `limit` caracteres, cortando lo mas tarde posible.

    Primero por parrafo, despues por oracion y, solo si una oracion sola excede el limite,
    por corte duro. Ese ultimo caso aparece con PDF sin puntuacion reconocible.
    """
    units: list[str] = []
    for paragraph in _split_paragraphs(text):
        if len(paragraph) <= limit:
            units.append(paragraph)
            continue
        buffer = ""
        for sentence in re.split(r"(?<=[.;:])\s+", paragraph):
            if buffer and len(buffer) + len(sentence) + 1 <= limit:
                buffer = f"{buffer} {sentence}"
                continue
            if buffer:
                units.append(buffer)
                buffer = ""
            while len(sentence) > limit:
                units.append(sentence[:limit])
                sentence = sentence[limit:]
            buffer = sentence
        if buffer:
            units.append(buffer)
    return units


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """Reagrupa el texto en piezas de a lo sumo `max_chars`, con overlap entre piezas.

    Las unidades atomicas se acotan a `max_chars - overlap` para que al arrancar una pieza
    nueva con la cola de la anterior el resultado siga entrando en el limite.
    """
    overlap = max(0, min(overlap, max_chars // 2))
    limit = max(max_chars - overlap - 2, max_chars // 2)

    pieces: list[str] = []
    buffer = ""
    for unit in _atomic_units(text, limit):
        candidate = f"{buffer}\n\n{unit}" if buffer else unit
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            pieces.append(buffer)
        tail = buffer[-overlap:] if overlap and buffer else ""
        with_tail = f"{tail}\n\n{unit}" if tail else unit
        buffer = with_tail if len(with_tail) <= max_chars else unit
    if buffer:
        pieces.append(buffer)
    return pieces


def _structured_segments(text: str) -> list[_Segment]:
    matches = list(_ARTICLE_RE.finditer(text))
    headings = _headings_by_position(text)
    segments: list[_Segment] = []

    preamble = text[: matches[0].start()].strip()
    if preamble:
        segments.append(_Segment(text=preamble, heading=_heading_at(headings, 0)))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start() : end].strip()
        if not body:
            continue
        segments.append(
            _Segment(
                text=body,
                heading=_heading_at(headings, match.start()),
                articulo=_normalize_article_number(match.group(1)),
            )
        )
    return segments


def _merge_small(segments: list[_Segment], max_chars: int, min_chars: int) -> list[_Segment]:
    """Agrupa segmentos consecutivos cortos que comparten encabezado."""
    merged: list[_Segment] = []
    for segment in segments:
        if not merged:
            merged.append(segment)
            continue
        previous = merged[-1]
        combined_length = len(previous.text) + len(segment.text) + 2
        can_merge = (
            len(previous.text) < min_chars
            and combined_length <= max_chars
            and previous.heading == segment.heading
        )
        if can_merge:
            previous.text = f"{previous.text}\n\n{segment.text}"
            if previous.articulo and segment.articulo:
                first = previous.articulo.split("-")[0]
                previous.articulo = f"{first}-{segment.articulo}"
            else:
                previous.articulo = previous.articulo or segment.articulo
        else:
            merged.append(segment)
    return merged


def chunk_document(
    text: str,
    *,
    max_chars: int = 1800,
    min_chars: int = 250,
    overlap: int = 200,
) -> list[Chunk]:
    text = text.strip()
    if not text:
        return []

    article_matches = list(_ARTICLE_RE.finditer(text))
    is_structured = len(article_matches) >= _MIN_ARTICLES_FOR_STRUCTURED or (
        bool(article_matches) and article_matches[0].start() <= _ARTICLE_HEAD_WINDOW
    )
    if is_structured:
        segments = _merge_small(_structured_segments(text), max_chars, min_chars)
    else:
        headings = _headings_by_position(text)
        segments = []
        cursor = 0
        for paragraph in _split_paragraphs(text):
            position = text.find(paragraph, cursor)
            cursor = position + len(paragraph) if position >= 0 else cursor
            segments.append(
                _Segment(text=paragraph, heading=_heading_at(headings, max(position, 0)))
            )
        segments = _merge_small(segments, max_chars, min_chars)

    chunks: list[Chunk] = []
    for segment in segments:
        pieces = (
            [segment.text]
            if len(segment.text) <= max_chars
            else _split_long(segment.text, max_chars, overlap)
        )
        total = len(pieces)
        for part_index, piece in enumerate(pieces):
            # En un articulo partido, las partes 2..n pierden el "ARTICULO N" del texto,
            # asi que se lo vuelve a poner como prefijo explicito.
            content = piece
            if segment.articulo and part_index > 0:
                content = f"[Art. {segment.articulo} (cont. {part_index + 1}/{total})]\n{piece}"
            chunks.append(
                Chunk(
                    content=content.strip(),
                    heading=segment.heading,
                    articulo=segment.articulo,
                )
            )

    for index, chunk in enumerate(chunks):
        chunk.chunk_index = index
    return [chunk for chunk in chunks if chunk.content]


def build_embedding_input(chunk: Chunk, document_title: str) -> str:
    """Texto que efectivamente se embeddea.

    Se le antepone el titulo del documento y la referencia estructural: sin eso, un chunk
    que dice "El plazo sera de treinta dias" es indistinguible entre la LCT y el CCyC.
    """
    prefix_parts = [document_title]
    if chunk.heading:
        prefix_parts.append(chunk.heading)
    if chunk.articulo:
        prefix_parts.append(f"Art. {chunk.articulo}")
    return " | ".join(prefix_parts) + "\n" + chunk.content
