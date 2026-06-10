# survey API 엔드포인트
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_id, get_db
from app.survey.schemas import (
    SurveyQuestionResponse,
    SurveySubmitRequest,
    SurveySubmitResponse,
)
from app.survey.service import list_survey_questions, submit_survey

router = APIRouter(prefix="/surveys", tags=["설문조사"])


@router.get(
    "/questions",
    response_model=list[SurveyQuestionResponse],
    summary="설문 문항 목록 조회",
    description="활성화된 설문 문항을 표시 순서대로 조회합니다.",
)
async def get_questions(db: AsyncSession = Depends(get_db)):
    questions = await list_survey_questions(db)
    return [
        SurveyQuestionResponse(
            question_id=question.id,
            question_text=question.question_text,
            stat_axis=question.stat_axis.value,
            display_order=question.display_order,
        )
        for question in questions
    ]


@router.post(
    "/submit",
    response_model=SurveySubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="설문 응답 제출",
    description=(
        "사용자가 제출한 설문 응답을 기반으로 6대 성향 점수를 계산하고 "
        "최신 성향 분석 결과를 user_stats 테이블에 저장합니다."
    ),
)
async def submit(
    payload: SurveySubmitRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    user_stats, stats = await submit_survey(db, payload, user_id)

    return SurveySubmitResponse(
        user_stats_id=user_stats.id,
        stats=stats,
        source_type=user_stats.source_type.value,
        survey_mode=user_stats.survey_mode.value,
    )
