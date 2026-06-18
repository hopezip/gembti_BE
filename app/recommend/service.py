# 추천 생성 전체 흐름 및 warning_list 분리
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.recommendation.schemas import _rating_from_score
from app.core.recommendation.similarity import cosine_similarity
from app.core.recommendation.vectorizer import user_stats_to_vector
from app.recommend.repository import (
    get_latest_recommendation_items,
    get_latest_user_stats,
    get_recommendable_games,
    get_user_library_steam_app_ids,
    save_recommendation_items,
)
from app.recommend.schemas import (
    DiscountedRecommendationsResponse,
    DiscountedRecommendedGameResponse,
    HighlyRatedRecommendationsResponse,
    HighlyRatedRecommendedGameResponse,
    PopularRecommendationsResponse,
    PopularRecommendedGameResponse,
    RecommendationGenerateResponse,
    RecommendedGameResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.game.models import Game
    from app.recommend.models import RecommendationItem


def build_recommended_game_response(
    recommendation_item: RecommendationItem,
    game: Game,
    similarity_score: float,
) -> RecommendedGameResponse:
    return RecommendedGameResponse(
        recommendation_item_id=recommendation_item.id,
        game_id=game.id,
        title=game.title,
        image_url=game.image_url,
        genres=list(game.genres),
        rating=_rating_from_score(game.review_score),
        similarity_score=float(round(similarity_score, 6)),
        similarity_rank=recommendation_item.similarity_rank,
    )


def normalize_percent_score(score: float | None) -> float:
    if score is None:
        return 0.0

    return max(0.0, min(float(score) / 100, 1.0))


def normalize_count_score(count: int | None) -> float:
    if count is None or count <= 0:
        return 0.0

    return min(math.log10(count + 1) / 6, 1.0)


def calculate_recommendation_sort_score(
    game: Game,
    similarity_score: float,
) -> float:
    review_score = normalize_percent_score(game.review_score)
    review_count_score = normalize_count_score(game.review_count)
    current_players_score = normalize_count_score(game.current_players)

    return (
        similarity_score * 0.55
        + review_score * 0.10
        + review_count_score * 0.20
        + current_players_score * 0.15
    )


async def generate_recommendations(
    db: AsyncSession,
    user_id: int,
    limit: int = 12,
) -> RecommendationGenerateResponse:
    user_stats = await get_latest_user_stats(db, user_id)
    if user_stats is None:
        raise BadRequestException("성향 스탯이 없습니다. 설문을 먼저 완료해 주세요.")

    owned_steam_app_ids = await get_user_library_steam_app_ids(db, user_id)
    games = await get_recommendable_games(db, excluded_app_ids=owned_steam_app_ids)
    if not games:
        raise BadRequestException("추천 가능한 게임 데이터가 없습니다.")

    user_vector = user_stats_to_vector(user_stats)
    scored_games = []

    for game in games:
        similarity_score = cosine_similarity(
            user_vector,
            [float(value) for value in game.trait_vector],
        )
        sort_score = calculate_recommendation_sort_score(
            game=game,
            similarity_score=similarity_score,
        )
        scored_games.append((game, similarity_score, sort_score))

    ranked_scored_games = sorted(
        scored_games,
        key=lambda item: item[2],
        reverse=True,
    )[:limit]

    ranked_games = [
        (game, similarity_score) for game, similarity_score, sort_score in ranked_scored_games
    ]

    recommendation_items = await save_recommendation_items(
        db=db,
        user_id=user_id,
        user_stats=user_stats,
        ranked_games=ranked_games,
    )
    await db.commit()

    response_games = [
        build_recommended_game_response(
            recommendation_item=recommendation_item,
            game=game,
            similarity_score=similarity_score,
        )
        for recommendation_item, (game, similarity_score) in zip(
            recommendation_items,
            ranked_games,
            strict=True,
        )
    ]

    return RecommendationGenerateResponse(games=response_games)


async def get_latest_recommendations(
    db: AsyncSession,
    user_id: int,
) -> RecommendationGenerateResponse:
    recommendation_items = await get_latest_recommendation_items(db, user_id)

    if not recommendation_items:
        raise NotFoundException("추천 기록 없음")

    response_games = [
        build_recommended_game_response(
            recommendation_item=recommendation_item,
            game=recommendation_item.game,
            similarity_score=float(recommendation_item.similarity_score),
        )
        for recommendation_item in recommendation_items
    ]

    return RecommendationGenerateResponse(games=response_games)


def calculate_sale_price(
    original_price_krw: int | None,
    discount_percent: int,
) -> int | None:
    if original_price_krw is None:
        return None

    if discount_percent <= 0:
        return None

    return int(original_price_krw * (1 - discount_percent / 100))


async def get_discounted_recommendations(
    db: AsyncSession,
    user_id: int,
    limit: int = 12,
) -> DiscountedRecommendationsResponse:
    recommendation_items = await get_latest_recommendation_items(db, user_id)

    if not recommendation_items:
        raise NotFoundException("추천 기록 없음")

    discounted_items = [item for item in recommendation_items if item.game.discount_percent > 0]

    if not discounted_items:
        raise NotFoundException("세일 중인 맞춤 게임 없음")

    response_games = [
        DiscountedRecommendedGameResponse(
            recommendation_item_id=item.id,
            game_id=item.game.id,
            title=item.game.title,
            image_url=item.game.image_url,
            genres=list(item.game.genres),
            price_krw=calculate_sale_price(
                item.game.price_krw,
                item.game.discount_percent,
            ),
            original_price_krw=item.game.price_krw,
            discount_percent=item.game.discount_percent,
            rating=_rating_from_score(item.game.review_score),
            similarity_score=float(item.similarity_score),
            similarity_rank=item.similarity_rank,
        )
        for item in discounted_items[:limit]
    ]

    return DiscountedRecommendationsResponse(games=response_games)


async def get_highly_rated_recommendations(
    db: AsyncSession,
    user_id: int,
    limit: int = 12,
    min_score: float = 80,
) -> HighlyRatedRecommendationsResponse:
    recommendation_items = await get_latest_recommendation_items(db, user_id)

    if not recommendation_items:
        raise NotFoundException("추천 기록 없음")

    highly_rated_items = [
        item
        for item in recommendation_items
        if item.game.review_score is not None and item.game.review_score >= min_score
    ]

    if not highly_rated_items:
        raise NotFoundException("평가가 좋은 맞춤 게임 없음")

    highly_rated_items = sorted(
        highly_rated_items,
        key=lambda item: (
            item.game.review_score or 0,
            -item.similarity_rank,
        ),
        reverse=True,
    )

    response_games = [
        HighlyRatedRecommendedGameResponse(
            recommendation_item_id=item.id,
            game_id=item.game.id,
            title=item.game.title,
            image_url=item.game.image_url,
            genres=list(item.game.genres),
            rating=_rating_from_score(item.game.review_score),
            review_count=item.game.review_count,
            similarity_score=float(item.similarity_score),
            similarity_rank=item.similarity_rank,
        )
        for item in highly_rated_items[:limit]
    ]

    return HighlyRatedRecommendationsResponse(games=response_games)


async def get_popular_recommendations(
    db: AsyncSession,
    user_id: int,
    limit: int = 12,
) -> PopularRecommendationsResponse:
    recommendation_items = await get_latest_recommendation_items(db, user_id)

    if not recommendation_items:
        raise NotFoundException("추천 기록 없음")

    popular_items = [
        item
        for item in recommendation_items
        if item.game.current_players is not None and item.game.current_players > 0
    ]

    if not popular_items:
        raise NotFoundException("맞춤 인기 게임 없음")

    popular_items = sorted(
        popular_items,
        key=lambda item: item.game.current_players or 0,
        reverse=True,
    )

    response_games = [
        PopularRecommendedGameResponse(
            recommendation_item_id=item.id,
            rank=index,
            game_id=item.game.id,
            title=item.game.title,
            image_url=item.game.image_url,
            genres=list(item.game.genres),
            current_players=item.game.current_players or 0,
            rating=_rating_from_score(item.game.review_score),
            current_players_updated_at=item.game.current_players_updated_at,
            similarity_score=float(item.similarity_score),
            similarity_rank=item.similarity_rank,
        )
        for index, item in enumerate(popular_items[:limit], start=1)
    ]

    return PopularRecommendationsResponse(games=response_games)
