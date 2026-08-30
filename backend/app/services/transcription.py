"""Transcripción de audio con Gemini, para el input por voz de la UI.

Es el fallback del hook de voz: cuando el browser no expone Web Speech API (Firefox, o
Safari con permisos restringidos), la UI graba el audio y lo manda acá. El prompt sesga la
transcripción hacia vocabulario jurídico argentino, que es donde los transcriptores
genéricos fallan más ("elecé té" en lugar de "LCT", "artículo doscientos cuarenta y cinco"
en lugar de "artículo 245").
"""

from __future__ import annotations

import logging
from functools import lru_cache

from google import genai
from google.genai import types

from ..core.settings import get_settings

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 15 * 1024 * 1024

ALLOWED_MIME_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/aac",
    "audio/flac",
}

_PROMPT = """Transcribí este audio de un abogado argentino dictando una consulta jurídica.

Reglas:
- Español rioplatense. Devolvé únicamente la transcripción, sin comentarios ni comillas.
- Escribí en números los artículos, leyes y montos: "artículo 245", "Ley 27.401", "$500.000".
- Usá las siglas del foro cuando se pronuncien como tales: LCT, CCyC, CSJN, ART, AFIP,
  ARCA, ANSES, DNU, CPCCN, SCBA, CNAT.
- Puntuá de forma que el texto se lea como una consulta escrita.
- Si el audio es inaudible o está vacío, devolvé una cadena vacía."""


@lru_cache
def _client() -> genai.Client:
    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY no está configurada")
    return genai.Client(api_key=settings.google_api_key)


async def transcribe(audio: bytes, mime_type: str) -> str:
    settings = get_settings()
    response = await _client().aio.models.generate_content(
        model=settings.gemini_transcribe_model,
        contents=[
            types.Part.from_bytes(data=audio, mime_type=mime_type),
            types.Part.from_text(text=_PROMPT),
        ],
        config=types.GenerateContentConfig(temperature=0.0),
    )
    text = (response.text or "").strip()
    logger.info("transcripción completada: %s caracteres", len(text))
    return text
