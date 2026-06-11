from types import SimpleNamespace
from typing import cast

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import router as auth_router
from app.auth.models import LoginProvider, User, UserStatus
from app.auth.schemas import UserFlowStatus
from app.main import app


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/v1/auth/token/refresh")

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh Token이 없습니다."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("has_stats", "expected_status"),
    [
        (False, UserFlowStatus.NEEDS_SURVEY),
        (True, UserFlowStatus.READY),
    ],
)
async def test_me_api_returns_user_flow_status(
    monkeypatch: pytest.MonkeyPatch,
    has_stats: bool,
    expected_status: UserFlowStatus,
) -> None:
    user = cast(
        "User",
        SimpleNamespace(
            id=7,
            email="test@example.com",
            nickname="tester",
            bio=None,
            login_provider=LoginProvider.EMAIL,
            status=UserStatus.ACTIVE,
            steam_linked=False,
            steam_id_64=None,
            steam_avatar_url=None,
            steam_sync_status=None,
            last_synced_at=None,
        ),
    )

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    async def has_user_stats(db: AsyncSession, user_id: int) -> bool:
        return has_stats

    monkeypatch.setattr(auth_router, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(auth_router, "has_user_stats", has_user_stats)

    response = await auth_router.me_api(user_id=7, db=cast("AsyncSession", object()))

    assert response.has_completed_survey is has_stats
    assert response.user_flow_status == expected_status
