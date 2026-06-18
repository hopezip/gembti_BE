from typing import cast

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.steam import router
from app.steam.models import SteamSyncStatus
from app.steam.schemas import SteamLinkRequest, SteamLinkResponse


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
        sync_response = await client.post("/api/v1/steam/sync")
        sync_status_response = await client.get("/api/v1/steam/sync/status/task-123")

    assert status_response.status_code == 404
    assert recent_response.status_code == 404
    assert sync_response.status_code == 404
    assert sync_status_response.status_code == 404


@pytest.mark.asyncio
async def test_steam_link_queues_library_sync_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_user_ids: list[int] = []

    class FakeSession:
        committed = False

        async def commit(self) -> None:
            self.committed = True

    async def link_steam_account(
        db: AsyncSession,
        user_id: int,
        steam_id: str,
    ) -> SteamLinkResponse:
        return SteamLinkResponse(
            steam_linked=True,
            steam_id_64=steam_id,
            steam_sync_status=SteamSyncStatus.FAILED,
        )

    async def enqueue_steam_library_sync_if_due(
        background_tasks: object,
        user_id: int,
        last_synced_at: object,
    ) -> None:
        queued_user_ids.append(user_id)

    monkeypatch.setattr(router, "link_steam_account", link_steam_account)
    monkeypatch.setattr(
        router,
        "enqueue_steam_library_sync_if_due",
        enqueue_steam_library_sync_if_due,
    )

    from fastapi import BackgroundTasks

    db = FakeSession()
    response = await router.steam_link_api(
        request=SteamLinkRequest(steam_id="76561198000000000"),
        background_tasks=BackgroundTasks(),
        user_id=7,
        db=cast("AsyncSession", db),
    )

    assert response.steam_linked is True
    assert db.committed is True
    assert queued_user_ids == [7]
