from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..core.db import SessionDep
from ..core.deps import CurrentUser
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from ..models import RefreshToken, User
from ..schemas.auth import LoginRequest, RefreshRequest, SignupRequest, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(session: SessionDep, user: User) -> TokenPair:
    access = create_access_token(user.id)
    refresh, expires_at = create_refresh_token(user.id)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=expires_at,
        )
    )
    session.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, session: SessionDep) -> TokenPair:
    email = payload.email.lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="ese email ya está registrado"
        )
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        estudio=payload.estudio,
        matricula=payload.matricula,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _issue_tokens(session, user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, session: SessionDep) -> TokenPair:
    user = session.exec(select(User).where(User.email == payload.email.lower())).first()
    # Mismo mensaje para email inexistente y password incorrecta: no se filtra si el
    # email esta registrado.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="credenciales inválidas"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="usuario inactivo")
    return _issue_tokens(session, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    token_hash = hash_refresh_token(payload.refresh_token)
    stored = session.exec(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()
    if stored is None or stored.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token revocado"
        )
    if stored.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token vencido"
        )

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="usuario inválido")

    # Rotacion: el refresh usado se invalida y se emite uno nuevo.
    stored.revoked_at = datetime.now(UTC)
    session.add(stored)
    return _issue_tokens(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, session: SessionDep) -> None:
    token_hash = hash_refresh_token(payload.refresh_token)
    stored = session.exec(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        session.add(stored)
        session.commit()


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
