from __future__ import annotations

import asyncio
from typing import TypedDict

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.survey.models import StatAxis, SurveyQuestion


class SurveyQuestionSeed(TypedDict):
    display_order: int
    stat_axis: str
    question_text: str


SURVEY_QUESTIONS: list[SurveyQuestionSeed] = [
    {
        "display_order": 1,
        "stat_axis": "combat",
        "question_text": "빠른 전투와 긴장감 있는 액션이 많은 게임을 선호한다.",
    },
    {
        "display_order": 2,
        "stat_axis": "strategy",
        "question_text": "자원 관리나 빌드 선택처럼 계획이 중요한 게임을 좋아한다.",
    },
    {
        "display_order": 3,
        "stat_axis": "cooperation",
        "question_text": "다른 사람과 역할을 나누어 함께 목표를 달성하는 플레이를 좋아한다.",
    },
    {
        "display_order": 4,
        "stat_axis": "exploration",
        "question_text": "넓은 세계를 돌아다니며 숨겨진 장소나 이야기를 발견하는 것을 좋아한다.",
    },
    {
        "display_order": 5,
        "stat_axis": "exploration",
        "question_text": "정해진 길보다 자유롭게 이동하며 나만의 방식으로 진행하는 게임을 선호한다.",
    },
    {
        "display_order": 6,
        "stat_axis": "growth",
        "question_text": "캐릭터, 장비, 능력치가 점점 강해지는 성장 과정이 중요하다.",
    },
    {
        "display_order": 7,
        "stat_axis": "growth",
        "question_text": "반복 플레이를 통해 보상을 모으고 목표를 달성하는 과정이 즐겁다.",
    },
    {
        "display_order": 8,
        "stat_axis": "healing",
        "question_text": "경쟁이나 압박보다 편안하게 즐길 수 있는 게임을 선호한다.",
    },
]


async def seed_survey_questions() -> None:
    async with AsyncSessionLocal() as db:
        for question_data in SURVEY_QUESTIONS:
            result = await db.execute(
                select(SurveyQuestion).where(
                    SurveyQuestion.display_order == question_data["display_order"],
                ),
            )
            question = result.scalar_one_or_none()

            if question is None:
                question = SurveyQuestion(
                    display_order=question_data["display_order"],
                    stat_axis=StatAxis(question_data["stat_axis"]),
                    question_text=question_data["question_text"],
                    is_active=True,
                )
                db.add(question)
            else:
                question.stat_axis = StatAxis(question_data["stat_axis"])
                question.question_text = question_data["question_text"]
                question.is_active = True

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_survey_questions())
