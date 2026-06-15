from typing import cast

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import router as auth_router
from app.main import app


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json() == {"error": "Refresh Token이 없습니다."}


@pytest.mark.asyncio
async def test_me_api_returns_service_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = object()

    async def get_me(db: AsyncSession, user_id: int):
        return user

    monkeypatch.setattr(auth_router, "get_me", get_me)

    response = await auth_router.me_api(user_id=7, db=cast("AsyncSession", object()))

    assert response == user
