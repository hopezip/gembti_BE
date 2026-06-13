from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.recommend import service
from app.stat.models import StatSourceType


@pytest.mark.asyncio
async def test_generate_recommendations_excludes_user_steam_library_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_stats = SimpleNamespace(
        id=1,
        combat=80,
        strategy=60,
        cooperation=40,
        exploration=70,
        growth=90,
        healing=30,
        source_type=StatSourceType.HYBRID_STEAM,
    )
    game = SimpleNamespace(
        id=100,
        app_id=30,
        title="Recommended Game",
        image_url=None,
        genres=["Action"],
        review_score=95.0,
        trait_vector=[80, 60, 40, 70, 90, 30],
    )
    captured_excluded_app_ids: list[int] | None = None

    async def get_latest_user_stats(db: AsyncSession, user_id: int):
        return user_stats

    async def get_user_library_steam_app_ids(db: AsyncSession, user_id: int) -> list[int]:
        return [10, 20]

    async def get_recommendable_games(
        db: AsyncSession,
        candidate_limit: int = 500,
        excluded_app_ids: list[int] | None = None,
    ):
        nonlocal captured_excluded_app_ids
        captured_excluded_app_ids = excluded_app_ids
        return [game]

    async def save_recommendation_items(
        db: AsyncSession,
        user_id: int,
        user_stats,
        ranked_games,
    ):
        return [SimpleNamespace(id=1, similarity_rank=1)]

    class FakeSession:
        committed = False

        async def commit(self) -> None:
            self.committed = True

    monkeypatch.setattr(service, "get_latest_user_stats", get_latest_user_stats)
    monkeypatch.setattr(
        service,
        "get_user_library_steam_app_ids",
        get_user_library_steam_app_ids,
    )
    monkeypatch.setattr(service, "get_recommendable_games", get_recommendable_games)
    monkeypatch.setattr(service, "save_recommendation_items", save_recommendation_items)

    db = FakeSession()
    result = await service.generate_recommendations(cast("AsyncSession", db), user_id=1)

    assert captured_excluded_app_ids == [10, 20]
    assert db.committed is True
    assert result.games[0].game_id == 100
