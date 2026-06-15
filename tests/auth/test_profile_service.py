from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.models import Gender, LoginProvider, UserStatus
from app.auth.schemas import ProfileUpdateRequest


@pytest.mark.asyncio
async def test_get_me_returns_profile_and_steam_library_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=7,
        email="steam@example.com",
        nickname="steam80109780",
        bio=None,
        gender=Gender.MALE,
        birth_date=None,
        login_provider=LoginProvider.STEAM,
        status=UserStatus.ACTIVE,
        steam_linked=True,
        steam_id_64="76561198280109780",
        steam_avatar_url="https://cdn.example.com/avatar.jpg",
        steam_sync_status="success",
        last_synced_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    library_game = SimpleNamespace(
        steam_app_id=730,
        playtime_minutes=5700,
        last_played_at=datetime(2026, 5, 15, tzinfo=UTC),
        synced_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    game = SimpleNamespace(
        id=1,
        title="Counter-Strike 2",
        image_url="https://cdn.example.com/cs2.jpg",
        genres=["FPS", "Action"],
        review_score=Decimal("92.50"),
    )

    async def get_user_by_id(db: AsyncSession, user_id: int):
        return user

    async def get_user_steam_library_rows(db: AsyncSession, user_id: int):
        return [(library_game, game)]

    async def has_user_stats(db: AsyncSession, user_id: int) -> bool:
        return True

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(
        service,
        "get_user_steam_library_rows",
        get_user_steam_library_rows,
    )
    monkeypatch.setattr(service, "has_user_stats", has_user_stats)

    response = await service.get_me(cast("AsyncSession", object()), user_id=7)

    assert response.id == 7
    assert response.user_id == 7
    assert response.steam_linked is True
    assert response.steam_id == "76561198280109780"
    assert response.steam_id_64 == "76561198280109780"
    assert response.has_completed_survey is True
    assert response.user_flow_status == "READY"
    assert response.steam_library.library_game_count == 1
    assert response.steam_library.total_playtime_minutes == 5700
    assert response.steam_library.total_playtime_hours == 95.0
    assert response.steam_library.games[0].title == "Counter-Strike 2"
    assert response.steam_library.games[0].playtime_hours == 95.0
    assert response.steam_library.games[0].rating == 92.5


def test_build_library_game_response_uses_fallback_title_without_game() -> None:
    library_game = SimpleNamespace(
        steam_app_id=123,
        playtime_minutes=90,
        last_played_at=None,
        synced_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    response = service.build_library_game_response(library_game, None)

    assert response.title == "Steam App 123"
    assert response.playtime_hours == 1.5


@pytest.mark.asyncio
async def test_update_me_updates_profile_and_returns_latest_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=7,
        email="test@example.com",
        nickname="oldname",
        bio=None,
        gender=None,
        birth_date=None,
        login_provider=LoginProvider.EMAIL,
        status=UserStatus.ACTIVE,
        steam_linked=False,
        steam_id_64=None,
        steam_avatar_url=None,
        steam_sync_status=None,
        last_synced_at=None,
    )
    committed: list[bool] = []

    class FakeSession:
        async def commit(self) -> None:
            committed.append(True)

    async def get_user_by_id(db: AsyncSession, user_id: int):
        return user

    async def get_user_by_nickname(db: AsyncSession, nickname: str):
        return None

    async def get_user_steam_library_rows(db: AsyncSession, user_id: int):
        return []

    async def has_user_stats(db: AsyncSession, user_id: int) -> bool:
        return False

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "get_user_by_nickname", get_user_by_nickname)
    monkeypatch.setattr(
        service,
        "get_user_steam_library_rows",
        get_user_steam_library_rows,
    )
    monkeypatch.setattr(service, "has_user_stats", has_user_stats)

    response = await service.update_me(
        cast("AsyncSession", FakeSession()),
        user_id=7,
        request=ProfileUpdateRequest(
            nickname="newname",
            bio="hello",
            gender=Gender.OTHER,
        ),
    )

    assert committed == [True]
    assert user.nickname == "newname"
    assert user.bio == "hello"
    assert user.gender == Gender.OTHER
    assert response.nickname == "newname"
    assert response.steam_library.library_game_count == 0


@pytest.mark.asyncio
async def test_get_my_activity_returns_library_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=7,
        steam_linked=True,
        steam_sync_status="success",
    )
    library_game = SimpleNamespace(
        steam_app_id=570,
        playtime_minutes=120,
        last_played_at=datetime(2026, 5, 15, tzinfo=UTC),
        synced_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    async def get_user_by_id(db: AsyncSession, user_id: int):
        return user

    async def get_user_steam_library_rows(db: AsyncSession, user_id: int):
        return [(library_game, None)]

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(
        service,
        "get_user_steam_library_rows",
        get_user_steam_library_rows,
    )

    response = await service.get_my_activity(cast("AsyncSession", object()), user_id=7)

    assert response.user_id == 7
    assert response.steam_linked is True
    assert response.steam_sync_status == "success"
    assert response.library_game_count == 1
    assert response.total_playtime_minutes == 120
    assert response.total_playtime_hours == 2.0
    assert response.recent_games[0].title == "Steam App 570"
