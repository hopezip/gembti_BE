from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import uuid4

import bcrypt
from jose import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    provider: str | None = None,
) -> str:
    issued_at = datetime.now(UTC)
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, str | int | datetime] = {
        "sub": str(subject),
        "exp": expire,
        "iat": int(issued_at.timestamp()),
        "jti": str(uuid4()),
        "type": "access",
    }
    if provider is not None:
        payload["provider"] = provider

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str) -> dict:
    """JWTError를 그대로 raise — 호출자가 처리."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
