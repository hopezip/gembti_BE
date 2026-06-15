# recommendation Request/Response 스키마
from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, Field


class RecommendedGameResponse(BaseModel):
    recommendation_item_id: int = Field(description="저장된 추천 결과 항목 ID")
    game_id: int = Field(description="추천된 게임 ID")
    title: str = Field(description="게임명")
    image_url: str | None = Field(default=None, description="대표 이미지 URL")
    genres: list[str] = Field(description="게임 장르 목록")
    rating: float | None = Field(
        default=None, ge=0.0, le=5.0, description="5점 만점 기준 게임 평점"
    )
    similarity_score: float = Field(description="코사인 유사도 점수")
    similarity_rank: int = Field(description="추천 순위")


class RecommendationGenerateResponse(BaseModel):
    games: list[RecommendedGameResponse] = Field(description="추천 게임 목록")


class DiscountedRecommendedGameResponse(BaseModel):
    recommendation_item_id: int
    game_id: int
    title: str
    image_url: str | None = None
    genres: list[str]
    price_krw: int | None
    original_price_krw: int | None
    discount_percent: int
    rating: float | None = Field(default=None, ge=0.0, le=5.0)
    similarity_score: float
    similarity_rank: int


class DiscountedRecommendationsResponse(BaseModel):
    games: list[DiscountedRecommendedGameResponse]


class HighlyRatedRecommendedGameResponse(BaseModel):
    recommendation_item_id: int
    game_id: int
    title: str
    image_url: str | None = None
    genres: list[str]
    rating: float | None = Field(default=None, ge=0.0, le=5.0)
    review_count: int
    similarity_score: float
    similarity_rank: int


class HighlyRatedRecommendationsResponse(BaseModel):
    games: list[HighlyRatedRecommendedGameResponse]


class PopularRecommendedGameResponse(BaseModel):
    recommendation_item_id: int
    rank: int
    game_id: int
    title: str
    image_url: str | None = None
    genres: list[str]
    current_players: int
    rating: float | None = Field(default=None, ge=0.0, le=5.0)
    current_players_updated_at: datetime | None
    similarity_score: float
    similarity_rank: int


class PopularRecommendationsResponse(BaseModel):
    games: list[PopularRecommendedGameResponse]
