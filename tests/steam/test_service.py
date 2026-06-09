from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.steam import service
from app.steam.client import SteamLibraryVisibility, SteamOwnedGamesResult
from app.steam.models import SteamAccount, SteamSyncStatus, UserLibraryGame


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

    async def get_library_games_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> list[UserLibraryGame]:
        return [
            cast(
                "UserLibraryGame",
                SimpleNamespace(steam_app_id=10, playtime_minutes=120),
            )
        ]

    monkeypatch.setattr(
        service,
        "get_steam_account_by_user_id",
        get_steam_account_by_user_id,
    )
    monkeypatch.setattr(
        service,
        "get_library_games_by_user_id",
        get_library_games_by_user_id,
    )

    result = await service.get_steam_status(cast("AsyncSession", object()), user_id=1)

    assert result.steam_linked is True
    assert result.steam_id_64 == "76561198000000000"
    assert result.steam_avatar_url == "https://cdn.example/avatar.jpg"
    assert result.steam_sync_status == SteamSyncStatus.SUCCESS
    assert result.library_games_count == 1
    assert result.next == service.STEAM_NEXT_RECOMMENDATION


@pytest.mark.asyncio
async def test_sync_steam_library_saves_public_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_account = cast(
        "SteamAccount",
        SimpleNamespace(
            steam_id_64=76561198000000000,
            steam_sync_status=SteamSyncStatus.FAILED,
            last_synced_at=None,
        ),
    )
    saved_games: list[UserLibraryGame] = []

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount | None:
        return steam_account

    async def get_owned_games(steam_id_64: int) -> SteamOwnedGamesResult:
        return SteamOwnedGamesResult(
            visibility=SteamLibraryVisibility.PUBLIC,
            games=[
                {
                    "appid": 10,
                    "playtime_forever": 120,
                    "rtime_last_played": 1_700_000_000,
                },
                {
                    "appid": 20,
                    "playtime_forever": 0,
                },
            ],
        )

    async def upsert_library_games(
        db: AsyncSession,
        user_id: int,
        games: list[UserLibraryGame],
    ) -> int:
        saved_games.extend(games)
        return len(games)

    class FakeSession:
        flushed = False

        async def flush(self) -> None:
            self.flushed = True

    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "get_owned_games", get_owned_games)
    monkeypatch.setattr(service, "upsert_library_games", upsert_library_games)

    db = FakeSession()
    result = await service.sync_steam_library(cast("AsyncSession", db), user_id=1)

    assert result.steam_sync_status == SteamSyncStatus.SUCCESS
    assert result.synced_count == 2
    assert result.next == service.STEAM_NEXT_RECOMMENDATION
    assert steam_account.steam_sync_status == SteamSyncStatus.SUCCESS
    assert steam_account.last_synced_at is not None
    assert db.flushed is True
    assert [game.steam_app_id for game in saved_games] == [10, 20]
    assert saved_games[0].playtime_minutes == 120
    assert saved_games[0].last_played_at == datetime.fromtimestamp(1_700_000_000, tz=UTC)


@pytest.mark.asyncio
async def test_sync_steam_library_private_moves_to_survey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_account = cast(
        "SteamAccount",
        SimpleNamespace(
            steam_id_64=76561198000000000,
            steam_sync_status=SteamSyncStatus.FAILED,
            last_synced_at=None,
        ),
    )

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount | None:
        return steam_account

    async def get_owned_games(steam_id_64: int) -> SteamOwnedGamesResult:
        return SteamOwnedGamesResult(SteamLibraryVisibility.PRIVATE, [])

    class FakeSession:
        flushed = False

        async def flush(self) -> None:
            self.flushed = True

    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "get_owned_games", get_owned_games)

    db = FakeSession()
    result = await service.sync_steam_library(cast("AsyncSession", db), user_id=1)

    assert result.steam_sync_status == SteamSyncStatus.PRIVATE
    assert result.synced_count == 0
    assert result.next == service.STEAM_NEXT_SURVEY
    assert "비공개" in result.message
    assert steam_account.steam_sync_status == SteamSyncStatus.PRIVATE
    assert db.flushed is True
