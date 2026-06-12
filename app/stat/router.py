from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user_id, get_db
from app.stat.schemas import UserStatsResponse
from app.stat.service import get_my_latest_stats

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


AUTH_ERROR_RESPONSE = {
    "description": "인증 실패",
    "content": {"application/json": {"example": {"error": "인증이 필요합니다."}}},
}

SERVER_ERROR_RESPONSE = {
    "description": "서버 내부 오류",
    "content": {"application/json": {"example": {"error": "서버 내부 오류"}}},
}


router = APIRouter(prefix="/stats", tags=["스탯"])


@router.get(
    "/me",
    response_model=UserStatsResponse,
    summary="내 최신 성향 스탯 조회",
    description=(
        "로그인 사용자의 최신 최종 성향 스탯을 반환합니다. "
        "Steam 연동 데이터가 있으면 HYBRID_STEAM, 없으면 ONLY_SURVEY 기준 결과를 반환합니다."
    ),
    responses={
        401: AUTH_ERROR_RESPONSE,
        404: {
            "description": "성향 스탯 없음",
            "content": {
                "application/json": {
                    "example": {"error": "성향 스탯이 없습니다. 설문을 먼저 완료해 주세요."}
                }
            },
        },
        500: SERVER_ERROR_RESPONSE,
    },
)
async def get_my_stats(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> UserStatsResponse:
    return await get_my_latest_stats(db, user_id)
