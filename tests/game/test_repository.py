"""app/game/repository.py 통합 테스트

실제 테스트 DB를 사용한다 (conftest.py 의 db_session 픽스처).
현재 구현된 함수: upsert_game, get_all_app_ids
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.game.models import Game
from app.game.repository import get_all_app_ids, upsert_game

# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────


def _game_data(
    app_id: int = 730,
    title: str = "Counter-Strike 2",
    *,
    review_score: float | None = 95.0,
    review_count: int = 100000,
    current_players: int | None = 50000,
    is_active: bool = True,
    genres: list | None = None,
    steam_detail: dict | None = None,
) -> dict:
    return {
        "app_id": app_id,
        "title": title,
        "image_url": f"https://cdn.steam.com/{app_id}.jpg",
        "description": "A great game",
        "genres": genres or ["Action"],
        "category": ["Single-player"],
        "trait_vector": [0.5, 0.3, 0.1, 0.4, 0.2, 0.1],
        "release_date": date(2023, 1, 1),
        "price_krw": 0,
        "is_free": True,
        "is_korean_supported": True,
        "is_active": is_active,
        "steam_url": f"https://store.steampowered.com/app/{app_id}/",
        "review_score": review_score,
        "review_count": review_count,
        "current_players": current_players,
        "current_players_updated_at": None,
        "steam_detail_json": steam_detail or {},
    }


async def _get_by_app_id(session: AsyncSession, app_id: int) -> Game | None:
    result = await session.execute(select(Game).where(Game.app_id == app_id))
    return result.scalar_one_or_none()


# ── upsert_game ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_game_insert(db_session: AsyncSession):
    """신규 app_id → DB에 삽입된다."""
    await upsert_game(db_session, _game_data(app_id=99901))
    await db_session.commit()

    game = await _get_by_app_id(db_session, 99901)
    assert game is not None
    assert game.app_id == 99901
    assert game.title == "Counter-Strike 2"


@pytest.mark.asyncio
async def test_upsert_game_update_on_conflict(db_session: AsyncSession):
    """동일 app_id 재삽입 → title이 업데이트된다."""
    await upsert_game(db_session, _game_data(app_id=99902, title="Original"))
    await db_session.commit()

    await upsert_game(db_session, _game_data(app_id=99902, title="Updated"))
    await db_session.commit()

    game = await _get_by_app_id(db_session, 99902)
    assert game is not None
    assert game.title == "Updated"


@pytest.mark.asyncio
async def test_upsert_game_created_at_preserved(db_session: AsyncSession):
    """upsert 시 created_at은 최초 값을 유지한다."""
    await upsert_game(db_session, _game_data(app_id=99903, title="Before"))
    await db_session.commit()

    game_before = await _get_by_app_id(db_session, 99903)
    created_at = game_before.created_at

    await upsert_game(db_session, _game_data(app_id=99903, title="After"))
    await db_session.commit()

    game_after = await _get_by_app_id(db_session, 99903)
    assert game_after.created_at == created_at


@pytest.mark.asyncio
async def test_upsert_game_update_fields(db_session: AsyncSession):
    """upsert 시 _UPDATE_FIELDS 항목이 갱신된다."""
    await upsert_game(db_session, _game_data(app_id=99904, review_score=80.0, current_players=100))
    await db_session.commit()

    await upsert_game(db_session, _game_data(app_id=99904, review_score=95.0, current_players=9999))
    await db_session.commit()

    game = await _get_by_app_id(db_session, 99904)
    assert float(game.review_score) == 95.0
    assert game.current_players == 9999


@pytest.mark.asyncio
async def test_upsert_game_inactive_stored(db_session: AsyncSession):
    """is_active=False 게임도 저장된다."""
    await upsert_game(db_session, _game_data(app_id=99905, is_active=False))
    await db_session.commit()

    game = await _get_by_app_id(db_session, 99905)
    assert game is not None
    assert game.is_active is False


# ── get_all_app_ids ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_app_ids_contains_inserted(db_session: AsyncSession):
    """삽입한 app_id들이 목록에 포함된다."""
    for app_id in [88801, 88802, 88803]:
        await upsert_game(db_session, _game_data(app_id=app_id))
    await db_session.commit()

    ids = await get_all_app_ids(db_session)
    assert 88801 in ids
    assert 88802 in ids
    assert 88803 in ids


@pytest.mark.asyncio
async def test_get_all_app_ids_no_duplicates(db_session: AsyncSession):
    """동일 app_id를 두 번 upsert해도 목록에 중복이 없다."""
    await upsert_game(db_session, _game_data(app_id=88811, title="First"))
    await db_session.commit()
    await upsert_game(db_session, _game_data(app_id=88811, title="Second"))
    await db_session.commit()

    ids = await get_all_app_ids(db_session)
    assert ids.count(88811) == 1


@pytest.mark.asyncio
async def test_get_all_app_ids_returns_list(db_session: AsyncSession):
    """반환 타입이 list[int]다."""
    ids = await get_all_app_ids(db_session)
    assert isinstance(ids, list)
    for id_ in ids:
        assert isinstance(id_, int)
