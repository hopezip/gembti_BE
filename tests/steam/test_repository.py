from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.steam.models import UserLibraryGame
from app.steam.repository import upsert_library_games


def library_game(user_id: int, steam_app_id: int, playtime_minutes: int = 0) -> UserLibraryGame:
    return UserLibraryGame(
        user_id=user_id,
        steam_app_id=steam_app_id,
        playtime_minutes=playtime_minutes,
        synced_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_upsert_library_games_reconciles_latest_snapshot() -> None:
    existing_game = library_game(user_id=1, steam_app_id=20, playtime_minutes=20)
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [existing_game]
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=[MagicMock(), select_result])
    db.flush = AsyncMock()

    synced_count = await upsert_library_games(
        cast("AsyncSession", db),
        user_id=1,
        games=[
            library_game(user_id=1, steam_app_id=20, playtime_minutes=200),
            library_game(user_id=1, steam_app_id=30, playtime_minutes=300),
        ],
    )

    stale_delete = db.execute.await_args_list[0].args[0]
    assert "user_library_games.user_id" in str(stale_delete)
    assert "steam_app_id NOT IN" in str(stale_delete)
    assert existing_game.playtime_minutes == 200
    assert db.add.call_args.args[0].steam_app_id == 30
    assert synced_count == 2
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_library_games_clears_public_empty_library() -> None:
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.flush = AsyncMock()

    synced_count = await upsert_library_games(cast("AsyncSession", db), user_id=1, games=[])

    delete_statement = db.execute.await_args.args[0]
    assert "user_library_games.user_id" in str(delete_statement)
    assert synced_count == 0
    db.flush.assert_awaited_once()
