from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_current_user_id, get_db
from app.recommend.schemas import (
    DiscountedRecommendationsResponse,
    HighlyRatedRecommendationsResponse,
    PopularRecommendationsResponse,
    RecommendationGenerateResponse,
)
from app.recommend.service import (
    generate_recommendations,
    get_discounted_recommendations,
    get_highly_rated_recommendations,
    get_latest_recommendations,
    get_popular_recommendations,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/recommendations", tags=["추천"])


@router.post(
    "/generate",
    response_model=RecommendationGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="추천 게임 목록 생성",
    description=(
        "로그인 사용자의 최신 성향 스탯과 게임 벡터를 코사인 유사도로 비교해 "
        "추천 게임 목록을 생성하고 recommendation_items 테이블에 저장합니다."
    ),
    responses={
        400: {
            "description": "추천 생성 불가",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_user_stats": {
                            "summary": "성향 스탯 없음",
                            "value": {"error": "성향 스탯이 없습니다. 설문을 먼저 완료해 주세요."},
                        },
                        "missing_games": {
                            "summary": "추천 가능한 게임 없음",
                            "value": {"error": "추천 가능한 게임 데이터가 없습니다."},
                        },
                    }
                }
            },
        },
        401: {
            "description": "인증 실패",
            "content": {"application/json": {"example": {"error": "인증이 필요합니다."}}},
        },
        422: {
            "description": "요청 형식 오류",
            "content": {
                "application/json": {"example": {"error": "요청 형식이 올바르지 않습니다."}}
            },
        },
        500: {
            "description": "서버 내부 오류",
            "content": {"application/json": {"example": {"error": "서버 내부 오류"}}},
        },
    },
)
async def generate(
    limit: int = Query(default=12, ge=1, le=50, description="반환할 추천 게임 개수"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await generate_recommendations(db=db, user_id=user_id, limit=limit)


@router.get(
    "/latest_reco",
    response_model=RecommendationGenerateResponse,
    summary="최신 추천 결과 조회",
    description="로그인 사용자의 가장 최근 추천 게임 목록을 조회합니다.",
    responses={
        401: {
            "description": "인증 실패",
            "content": {"application/json": {"example": {"error": "인증이 필요합니다."}}},
        },
        404: {
            "description": "추천 기록 없음",
            "content": {"application/json": {"example": {"error": "추천 기록 없음"}}},
        },
        500: {
            "description": "서버 내부 오류",
            "content": {"application/json": {"example": {"error": "서버 내부 오류"}}},
        },
    },
)
async def latest_reco(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await get_latest_recommendations(db=db, user_id=user_id)


@router.get(
    "/discounted",
    response_model=DiscountedRecommendationsResponse,
    summary="세일 중인 맞춤 게임 조회",
    description="로그인 사용자의 최신 추천 결과 중 할인 중인 게임만 추천 순위 순서로 조회합니다.",
)
async def discounted(
    limit: int = Query(default=12, ge=1, le=50, description="반환할 게임 개수"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await get_discounted_recommendations(db=db, user_id=user_id, limit=limit)


@router.get(
    "/highly-rated",
    response_model=HighlyRatedRecommendationsResponse,
    summary="평가가 좋은 맞춤 게임 조회",
    description="로그인 사용자의 최신 추천 결과 중 평점이 높은 게임을 조회합니다.",
)
async def highly_rated(
    limit: int = Query(default=12, ge=1, le=50, description="반환할 게임 개수"),
    min_score: float = Query(default=80, ge=0, le=100, description="최소 Steam 긍정 평가율"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await get_highly_rated_recommendations(
        db=db,
        user_id=user_id,
        limit=limit,
        min_score=min_score,
    )


@router.get(
    "/popular",
    response_model=PopularRecommendationsResponse,
    summary="맞춤 인기 게임 조회",
    description="로그인 사용자의 최신 추천 결과 중 동시 접속자 수가 높은 게임을 조회합니다.",
)
async def popular(
    limit: int = Query(default=12, ge=1, le=50, description="반환할 게임 개수"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await get_popular_recommendations(db=db, user_id=user_id, limit=limit)
