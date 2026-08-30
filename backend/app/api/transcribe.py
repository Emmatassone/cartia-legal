import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..core.deps import CurrentUser
from ..services.transcription import ALLOWED_MIME_TYPES, MAX_AUDIO_BYTES, transcribe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voz"])


class TranscriptionOut(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscriptionOut)
async def transcribe_audio(
    user: CurrentUser, audio: Annotated[UploadFile, File()]
) -> TranscriptionOut:
    mime_type = (audio.content_type or "").split(";")[0].strip().lower()
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"formato de audio no soportado: {mime_type or 'desconocido'}",
        )

    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="el audio llegó vacío")
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="el audio supera el máximo de 15 MB",
        )

    try:
        text = await transcribe(payload, mime_type)
    except Exception as exc:
        logger.exception("falló la transcripción")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="no se pudo transcribir el audio",
        ) from exc

    return TranscriptionOut(text=text)
