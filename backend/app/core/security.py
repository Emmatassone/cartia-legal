import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from .settings import get_settings

_settings = get_settings()


# bcrypt trunca en 72 bytes. Se pre-hashea con SHA-256 para que una passphrase larga
# no pierda entropia de forma silenciosa.
def _prepare(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: UUID) -> str:
    return _encode(user_id, "access", timedelta(minutes=_settings.access_token_minutes))


def create_refresh_token(user_id: UUID) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(days=_settings.refresh_token_days)
    token = _encode(user_id, "refresh", timedelta(days=_settings.refresh_token_days))
    return token, expires_at


def _encode(user_id: UUID, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> UUID:
    try:
        payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("token expirado") from exc
    except jwt.PyJWTError as exc:
        raise ValueError("token invalido") from exc
    if payload.get("type") != expected_type:
        raise ValueError("tipo de token incorrecto")
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise ValueError("token sin subject valido") from exc


def hash_refresh_token(token: str) -> str:
    """Los refresh tokens se guardan hasheados: si se filtra la tabla, no son usables."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
