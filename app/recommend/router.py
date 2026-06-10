from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_current_user_id, get_db
from app.recommend.schemas import RecommendationGenerateResponse
from app.recommend.service import generate_recommendations

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
)
async def generate(
    limit: int = Query(default=10, ge=1, le=50, description="반환할 추천 게임 개수"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await generate_recommendations(db=db, user_id=user_id, limit=limit)
