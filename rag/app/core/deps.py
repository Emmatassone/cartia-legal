from typing import Annotated

from fastapi import Header, HTTPException, status

from .settings import get_settings


def require_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    """El servicio RAG solo se expone al backend, nunca al browser."""
    expected = get_settings().internal_token
    if not x_internal_token or x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal token",
        )
