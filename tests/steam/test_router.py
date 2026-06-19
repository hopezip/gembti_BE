from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app
from app.steam import router


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
