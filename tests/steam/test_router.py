from httpx import ASGITransport, AsyncClient
import pytest

from app.core.dependencies import get_current_user_id
from app.main import app
from app.steam import router
from app.steam.models import SteamSyncStatus
from app.steam.schemas import SteamSyncResponse, SteamUnlinkResponse


@pytest.mark.asyncio
async def test_steam_auth_login_redirects_to_steam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        router,
        "build_steam_login_url",
        lambda: "https://steamcommunity.com/openid/login?openid.mode=checkid_setup",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        follow_redirects=False,
    ) as client:
        response = await client.get("/api/v1/auth/steam")

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://steamcommunity.com/openid/login")


@pytest.mark.asyncio
async def test_removed_steam_helper_routes_return_404() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        status_response = await client.get("/api/v1/steam/status")
        recent_response = await client.get("/api/v1/steam/recently-played")
        sync_status_response = await client.get("/api/v1/steam/sync/status/task-123")
        link_response = await client.post("/api/v1/steam/link")

    assert status_response.status_code == 404
    assert recent_response.status_code == 404
    assert sync_status_response.status_code == 404
    assert link_response.status_code == 404


@pytest.mark.asyncio
async def test_steam_sync_returns_sync_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_current_user_id() -> int:
        return 1

    async def fake_sync(*args: object, **kwargs: object) -> SteamSyncResponse:
        return SteamSyncResponse(
            steam_sync_status=SteamSyncStatus.SUCCESS,
            synced_count=12,
            next="RECOMMENDATION",
            message="Steam 라이브러리 동기화가 완료되었습니다.",
        )

    app.dependency_overrides[get_current_user_id] = fake_current_user_id
    monkeypatch.setattr(router, "sync_steam_library_now", fake_sync)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            response = await client.post("/api/v1/steam/sync")
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)

    assert response.status_code == 200
    assert response.json()["synced_count"] == 12


@pytest.mark.asyncio
async def test_steam_unlink_returns_unlinked_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_current_user_id() -> int:
        return 1

    async def fake_unlink(*args: object, **kwargs: object) -> SteamUnlinkResponse:
        return SteamUnlinkResponse(message="Steam 계정 연동이 해제되었습니다.")

    app.dependency_overrides[get_current_user_id] = fake_current_user_id
    monkeypatch.setattr(router, "unlink_steam_account", fake_unlink)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            response = await client.delete("/api/v1/steam/unlink")
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)

    assert response.status_code == 200
    assert response.json() == {
        "steam_linked": False,
        "message": "Steam 계정 연동이 해제되었습니다.",
    }
