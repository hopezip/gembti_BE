# 추천 생성 전체 흐름 및 warning_list 분리
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import BadRequestException
from app.core.recommendation.similarity import cosine_similarity
from app.core.recommendation.vectorizer import user_stats_to_vector
from app.recommend.repository import (
    get_latest_user_stats,
    get_recommendable_games,
    get_user_library_steam_app_ids,
    save_recommendation_items,
)
from app.recommend.schemas import RecommendationGenerateResponse, RecommendedGameResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def generate_recommendations(
    db: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> RecommendationGenerateResponse:
    user_stats = await get_latest_user_stats(db, user_id)
    if user_stats is None:
        raise BadRequestException("성향 스탯이 없습니다. 설문을 먼저 완료해 주세요.")

    owned_steam_app_ids = await get_user_library_steam_app_ids(db, user_id)
    games = await get_recommendable_games(db, excluded_app_ids=owned_steam_app_ids)
    if not games:
        raise BadRequestException("추천 가능한 게임 데이터가 없습니다.")

    user_vector = user_stats_to_vector(user_stats)
    scored_games = [
        (game, cosine_similarity(user_vector, [float(value) for value in game.trait_vector]))
        for game in games
    ]
    ranked_games = sorted(scored_games, key=lambda item: item[1], reverse=True)[:limit]

    recommendation_items = await save_recommendation_items(
        db=db,
        user_id=user_id,
        user_stats=user_stats,
        ranked_games=ranked_games,
    )
    await db.commit()

    response_games = [
        RecommendedGameResponse(
            recommendation_item_id=recommendation_item.id,
            game_id=game.id,
            title=game.title,
            image_url=game.image_url,
            genres=list(game.genres),
            review_score=float(game.review_score) if game.review_score is not None else None,
            similarity_score=float(round(similarity_score, 6)),
            similarity_rank=recommendation_item.similarity_rank,
        )
        for recommendation_item, (game, similarity_score) in zip(
            recommendation_items,
            ranked_games,
            strict=True,
        )
    ]

    return RecommendationGenerateResponse(games=response_games)
