# 설문 응답 검증 및 성향 계산 요청 로직
from sqlalchemy.ext.asyncio import AsyncSession

from app.stat.calculator import calculate_user_stats
from app.stat.repository import create_user_stats
from app.survey.repository import get_active_questions


async def list_survey_questions(db: AsyncSession):
    return await get_active_questions(db)


async def submit_survey(db, request, user_id: int):
    questions = await get_active_questions(db)

    active_question_ids = {question.id for question in questions}
    submitted_question_ids = {answer.question_id for answer in request.answers}

    if len(submitted_question_ids) != len(request.answers):
        raise ValueError("중복된 설문 응답이 존재합니다.")

    if submitted_question_ids != active_question_ids:
        raise ValueError("모든 활성 설문 문항에 응답해야 합니다.")

    answers_by_question_id = {answer.question_id: answer.answer for answer in request.answers}

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
