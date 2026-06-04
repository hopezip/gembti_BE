from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token
# 이 파일 왜 있는지 여쭤볼 것
bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    if credentials is None:
        raise UnauthorizedException()
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedException("액세스 토큰이 아닙니다.")
        user_id = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException()
        return int(user_id)
    except (JWTError, ValueError):
        raise UnauthorizedException("유효하지 않은 토큰입니다.") from None
