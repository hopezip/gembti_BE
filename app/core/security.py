from datetime import UTC, datetime, timedelta
from typing import Literal, NotRequired, TypedDict, cast
from uuid import uuid4

import bcrypt
from jose import jwt

from app.core.config import settings


class TokenPayload(TypedDict):
    sub: str
    exp: int
    iat: int
    jti: str
    type: Literal["access", "refresh"]
    provider: NotRequired[str]


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
    expire = issued_at + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: TokenPayload = {
        "sub": str(subject),
        "exp": int(expire.timestamp()),
        "iat": int(issued_at.timestamp()),
        "jti": str(uuid4()),
        "type": "access",
    }
    if provider is not None:
        payload["provider"] = provider

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    provider: str | None = None,
) -> str:
    issued_at = datetime.now(UTC)
    expire = issued_at + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    payload: TokenPayload = {
        "sub": str(subject),
        "exp": int(expire.timestamp()),
        "iat": int(issued_at.timestamp()),
        "jti": str(uuid4()),
        "type": "refresh",
    }
    if provider is not None:
        payload["provider"] = provider

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """JWTError를 그대로 raise — 호출자가 처리."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    return cast("TokenPayload", payload)
