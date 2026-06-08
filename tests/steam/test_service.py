from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.steam import service
from app.steam.models import SteamAccount, SteamSyncStatus


def test_build_steam_login_url_contains_openid_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service.settings, "BACKEND_BASE_URL", "http://localhost:8000")

    url = service.build_steam_login_url()

    assert url.startswith("https://steamcommunity.com/openid/login?")
    assert "openid.mode=checkid_setup" in url
    assert (
        "openid.return_to=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fv1%2Fauth%2Fsteam%2Fcallback" in url
    )
    assert "openid.realm=http%3A%2F%2Flocalhost%3A8000" in url


def test_extract_steam_id_64() -> None:
    steam_id = service.extract_steam_id_64(
        {
            "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000000",
        }
    )

    assert steam_id == 76561198000000000


@pytest.mark.asyncio
async def test_get_steam_status_returns_unlinked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount | None:
        return None

    monkeypatch.setattr(
        service,
        "get_steam_account_by_user_id",
        get_steam_account_by_user_id,
    )

    result = await service.get_steam_status(cast("AsyncSession", object()), user_id=1)

    assert result.steam_linked is False
    assert result.steam_id_64 is None


@pytest.mark.asyncio
async def test_get_steam_status_returns_linked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_account = cast(
        "SteamAccount",
        SimpleNamespace(
            steam_id_64=76561198000000000,
            avatar_url="https://cdn.example/avatar.jpg",
            steam_sync_status=SteamSyncStatus.SUCCESS,
            last_synced_at=None,
        ),
    )

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount | None:
        return steam_account

    monkeypatch.setattr(
        service,
        "get_steam_account_by_user_id",
        get_steam_account_by_user_id,
    )

    result = await service.get_steam_status(cast("AsyncSession", object()), user_id=1)

    assert result.steam_linked is True
    assert result.steam_id_64 == "76561198000000000"
    assert result.steam_avatar_url == "https://cdn.example/avatar.jpg"
    assert result.steam_sync_status == SteamSyncStatus.SUCCESS
