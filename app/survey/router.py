# survey API 엔드포인트
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_id, get_db
from app.survey.schemas import (
    SurveyQuestionResponse,
    SurveyResultResponse,
    SurveySubmitRequest,
    SurveySubmitResponse,
)
from app.survey.service import (
    get_latest_survey_result,
    list_survey_questions,
    submit_survey,
)

AUTH_ERROR_RESPONSE = {
    "description": "인증 실패",
    "content": {"application/json": {"example": {"error": "인증이 필요합니다."}}},
}

VALIDATION_ERROR_RESPONSE = {
    "description": "요청 형식 오류",
    "content": {"application/json": {"example": {"error": "요청 형식이 올바르지 않습니다."}}},
}

SERVER_ERROR_RESPONSE = {
    "description": "서버 내부 오류",
    "content": {"application/json": {"example": {"error": "서버 내부 오류"}}},
}

router = APIRouter(prefix="/surveys", tags=["설문조사"])


@router.get(
    "/questions",
    response_model=list[SurveyQuestionResponse],
    summary="설문 문항 목록 조회",
    description="활성화된 설문 문항을 표시 순서대로 조회합니다.",
    responses={
        401: AUTH_ERROR_RESPONSE,
        500: SERVER_ERROR_RESPONSE,
    },
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
    responses={
        400: {
            "description": "설문 응답 검증 실패",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_answer": {
                            "summary": "응답 누락",
                            "value": {"error": "응답 누락 문항이 존재합니다."},
                        },
                        "duplicated_answer": {
                            "summary": "중복 응답",
                            "value": {"error": "중복된 설문 응답이 존재합니다."},
                        },
                        "unknown_question": {
                            "summary": "존재하지 않는 문항",
                            "value": {"error": "존재하지 않는 설문 문항 응답입니다."},
                        },
                    }
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
        500: SERVER_ERROR_RESPONSE,
    },
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


@router.get(
    "/result",
    response_model=SurveyResultResponse,
    summary="최근 설문 결과 조회",
    description="로그인 사용자의 가장 최근 설문 기반 성향 결과를 조회합니다.",
    responses={
        401: AUTH_ERROR_RESPONSE,
        404: {
            "description": "설문 기록 없음",
            "content": {"application/json": {"example": {"error": "설문 기록 없음"}}},
        },
        500: SERVER_ERROR_RESPONSE,
    },
)
async def get_result(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    user_stats = await get_latest_survey_result(db, user_id)

    return SurveyResultResponse(
        user_stats_id=user_stats.id,
        stats={
            "combat": user_stats.combat,
            "strategy": user_stats.strategy,
            "cooperation": user_stats.cooperation,
            "exploration": user_stats.exploration,
            "growth": user_stats.growth,
            "healing": user_stats.healing,
        },
        source_type=user_stats.source_type.value,
        survey_mode=user_stats.survey_mode.value if user_stats.survey_mode else None,
        created_at=user_stats.created_at.isoformat(),
    )
