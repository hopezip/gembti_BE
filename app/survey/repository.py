# seed_questions 조회
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.survey.models import SurveyQuestion


async def get_active_questions(db: AsyncSession) -> list[SurveyQuestion]:
    result = await db.execute(
        select(SurveyQuestion)
        .where(SurveyQuestion.is_active.is_(True))
        .order_by(SurveyQuestion.display_order)
    )
    return list(result.scalars().all())


async def get_questions_by_ids(
    db: AsyncSession,
    question_ids: list[int],
) -> list[SurveyQuestion]:
    result = await db.execute(select(SurveyQuestion).where(SurveyQuestion.id.in_(question_ids)))
    return list(result.scalars().all())
