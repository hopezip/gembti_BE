# 설문 응답 검증 및 성향 계산 요청 로직
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.stat.calculator import calculate_user_stats
from app.stat.repository import create_user_stats, get_latest_user_stats
from app.survey.repository import get_active_questions

ANSWER_SCORE_MAP = {
    1: -2,
    2: -1,
    3: 0,
    4: 1,
    5: 2,
}


def convert_answer_to_score(answer: int | None) -> int | None:
    if answer is None:
        return None
    return ANSWER_SCORE_MAP[answer]


async def list_survey_questions(db: AsyncSession):
    return await get_active_questions(db)


async def submit_survey(db, request, user_id: int):
    questions = await get_active_questions(db)

    active_question_ids = {question.id for question in questions}
    submitted_question_ids = {answer.question_id for answer in request.answers}

    if len(submitted_question_ids) != len(request.answers):
        raise BadRequestException("중복된 설문 응답이 존재합니다.")

    unknown_question_ids = submitted_question_ids - active_question_ids
    if unknown_question_ids:
        raise BadRequestException("존재하지 않는 설문 문항 응답입니다.")

    missing_question_ids = active_question_ids - submitted_question_ids
    if missing_question_ids:
        raise BadRequestException("응답 누락 문항이 존재합니다.")

    answers_by_question_id = {
        answer.question_id: convert_answer_to_score(answer.answer) for answer in request.answers
    }

    stats = calculate_user_stats(
        questions=questions,
        answers_by_question_id=answers_by_question_id,
    )

    user_stats = await create_user_stats(
        db=db,
        user_id=user_id,
        stats=stats,
    )
    await db.commit()
    await db.refresh(user_stats)

    return user_stats, stats


async def get_latest_survey_result(db: AsyncSession, user_id: int):
    user_stats = await get_latest_user_stats(db, user_id)
    if user_stats is None:
        raise NotFoundException("설문 기록 없음")
    return user_stats
