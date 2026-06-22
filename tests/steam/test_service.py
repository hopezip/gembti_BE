from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LoginProvider
from app.core.exceptions import (
    BadGatewayException,
    ForbiddenException,
    InternalServerErrorException,
    NotFoundException,
)
from app.steam import service
from app.steam.client import (
    SteamLibraryPayloadError,
    SteamLibraryVisibility,
    SteamOwnedGamesResult,
)
from app.steam.models import SteamAccount, SteamSyncStatus, UserLibraryGame
from app.steam.schemas import SteamSyncResponse


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
            game_count=2,
        )

    async def upsert_library_games(
        db: AsyncSession,
        user_id: int,
        games: list[UserLibraryGame],
    ) -> int:
        saved_games.extend(games)
        return len(games)

    async def count_library_games_by_user_id(db: AsyncSession, user_id: int) -> int:
        return len(saved_games)

    class FakeSession:
        flushed = False

        async def flush(self) -> None:
            self.flushed = True

    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "get_owned_games", get_owned_games)
    monkeypatch.setattr(service, "upsert_library_games", upsert_library_games)
    monkeypatch.setattr(
        service,
        "count_library_games_by_user_id",
        count_library_games_by_user_id,
    )

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
async def test_sync_steam_library_rejects_steam_api_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_account = cast(
        "SteamAccount",
        SimpleNamespace(steam_id_64=76561198000000000),
    )

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount | None:
        return steam_account

    async def get_owned_games(steam_id_64: int) -> SteamOwnedGamesResult:
        raise SteamLibraryPayloadError("Steam API 게임 수 불일치: reported=2, received=1")

    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "get_owned_games", get_owned_games)

    with pytest.raises(BadGatewayException, match="게임 수가 일치하지 않습니다"):
        await service.sync_steam_library(cast("AsyncSession", object()), user_id=1)


@pytest.mark.asyncio
async def test_sync_steam_library_rejects_stored_count_mismatch(
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
        return SteamOwnedGamesResult(
            SteamLibraryVisibility.PUBLIC,
            [{"appid": 10}, {"appid": 20}],
            game_count=2,
        )

    async def upsert_library_games(
        db: AsyncSession,
        user_id: int,
        games: list[UserLibraryGame],
    ) -> int:
        return len(games)

    async def count_library_games_by_user_id(db: AsyncSession, user_id: int) -> int:
        return 1

    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "get_owned_games", get_owned_games)
    monkeypatch.setattr(service, "upsert_library_games", upsert_library_games)
    monkeypatch.setattr(
        service,
        "count_library_games_by_user_id",
        count_library_games_by_user_id,
    )

    with pytest.raises(InternalServerErrorException, match="저장 결과"):
        await service.sync_steam_library(cast("AsyncSession", object()), user_id=1)


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


@pytest.mark.asyncio
async def test_sync_steam_library_empty_clears_stale_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_account = cast(
        "SteamAccount",
        SimpleNamespace(
            steam_id_64=76561198000000000,
            steam_sync_status=SteamSyncStatus.SUCCESS,
            last_synced_at=None,
        ),
    )
    saved_snapshots: list[list[UserLibraryGame]] = []

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount | None:
        return steam_account

    async def get_owned_games(steam_id_64: int) -> SteamOwnedGamesResult:
        return SteamOwnedGamesResult(SteamLibraryVisibility.EMPTY, [], game_count=0)

    async def upsert_library_games(
        db: AsyncSession,
        user_id: int,
        games: list[UserLibraryGame],
    ) -> int:
        saved_snapshots.append(games)
        return 0

    async def count_library_games_by_user_id(db: AsyncSession, user_id: int) -> int:
        return 0

    class FakeSession:
        async def flush(self) -> None:
            return None

    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "get_owned_games", get_owned_games)
    monkeypatch.setattr(service, "upsert_library_games", upsert_library_games)
    monkeypatch.setattr(
        service,
        "count_library_games_by_user_id",
        count_library_games_by_user_id,
    )

    result = await service.sync_steam_library(cast("AsyncSession", FakeSession()), user_id=1)

    assert saved_snapshots == [[]]
    assert result.steam_sync_status == SteamSyncStatus.EMPTY
    assert result.synced_count == 0
    assert result.next == service.STEAM_NEXT_SURVEY


@pytest.mark.asyncio
async def test_sync_steam_library_now_rolls_back_on_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def sync_steam_library(db: AsyncSession, user_id: int) -> SteamSyncResponse:
        raise InternalServerErrorException("저장 수 불일치")

    class FakeSession:
        committed = False
        rolled_back = False

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

    monkeypatch.setattr(service, "sync_steam_library", sync_steam_library)
    db = FakeSession()

    with pytest.raises(InternalServerErrorException):
        await service.sync_steam_library_now(cast("AsyncSession", db), user_id=1)

    assert db.committed is False
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_unlink_steam_account_deletes_email_users_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(login_provider=LoginProvider.EMAIL)
    deleted_user_ids: list[int] = []

    async def get_user_by_id(db: AsyncSession, user_id: int) -> object:
        return user

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> SteamAccount:
        return cast("SteamAccount", SimpleNamespace(user_id=user_id))

    async def delete_steam_connection(db: AsyncSession, user_id: int) -> None:
        deleted_user_ids.append(user_id)

    class FakeSession:
        committed = False

        async def commit(self) -> None:
            self.committed = True

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)
    monkeypatch.setattr(service, "delete_steam_connection", delete_steam_connection)

    db = FakeSession()
    result = await service.unlink_steam_account(cast("AsyncSession", db), user_id=7)

    assert result.steam_linked is False
    assert deleted_user_ids == [7]
    assert db.committed is True


@pytest.mark.asyncio
async def test_unlink_steam_account_rejects_steam_login_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_user_by_id(db: AsyncSession, user_id: int) -> object:
        return SimpleNamespace(login_provider=LoginProvider.STEAM)

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)

    with pytest.raises(ForbiddenException):
        await service.unlink_steam_account(cast("AsyncSession", object()), user_id=7)


@pytest.mark.asyncio
async def test_unlink_steam_account_requires_linked_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_user_by_id(db: AsyncSession, user_id: int) -> object:
        return SimpleNamespace(login_provider=LoginProvider.EMAIL)

    async def get_steam_account_by_user_id(
        db: AsyncSession,
        user_id: int,
    ) -> None:
        return None

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "get_steam_account_by_user_id", get_steam_account_by_user_id)

    with pytest.raises(NotFoundException):
        await service.unlink_steam_account(cast("AsyncSession", object()), user_id=7)
