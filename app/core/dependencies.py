from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.token_blacklist import is_access_token_blacklisted
from app.core.database import AsyncSessionLocal
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token

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
    except JWTError:
        raise UnauthorizedException("유효하지 않은 토큰입니다.") from None

    if payload.get("type") != "access":
        raise UnauthorizedException("액세스 토큰이 아닙니다.")

    if await is_access_token_blacklisted(credentials.credentials):
        raise UnauthorizedException("로그아웃된 액세스 토큰입니다.")

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException()

    try:
        return int(user_id)
    except ValueError:
        raise UnauthorizedException("유효하지 않은 토큰입니다.") from None
