from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pytest

from app.stat.calculator import calculate_user_stats, normalize_score


class FakeStatAxis(StrEnum):
    COMBAT = "combat"
    STRATEGY = "strategy"
    COOPERATION = "cooperation"
    EXPLORATION = "exploration"
    GROWTH = "growth"
    HEALING = "healing"


@dataclass(frozen=True)
class FakeSurveyQuestion:
    id: int
    stat_axis: FakeStatAxis


def test_normalize_score_returns_50_when_question_count_is_zero() -> None:
    assert normalize_score(raw_score=0, question_count=0) == 50


@pytest.mark.parametrize(
    ("raw_score", "question_count", "expected"),
    [
        (-4, 2, 0),
        (0, 2, 50),
        (4, 2, 100),
        (2, 2, 75),
    ],
)
def test_normalize_score_converts_raw_score_to_0_100_range(
    raw_score: int,
    question_count: int,
    expected: int,
) -> None:
    assert normalize_score(raw_score=raw_score, question_count=question_count) == expected


def test_calculate_user_stats_groups_answers_by_stat_axis() -> None:
    questions = [
        FakeSurveyQuestion(id=1, stat_axis=FakeStatAxis.COMBAT),
        FakeSurveyQuestion(id=2, stat_axis=FakeStatAxis.COMBAT),
        FakeSurveyQuestion(id=3, stat_axis=FakeStatAxis.STRATEGY),
        FakeSurveyQuestion(id=4, stat_axis=FakeStatAxis.HEALING),
    ]
    answers_by_question_id: dict[int, int | None] = {
        1: 2,
        2: 0,
        3: -2,
        4: 2,
    }

    stats = calculate_user_stats(
        questions=questions,
        answers_by_question_id=answers_by_question_id,
    )

    assert stats == {
        "combat": 75,
        "strategy": 0,
        "cooperation": 50,
        "exploration": 50,
        "growth": 50,
        "healing": 100,
    }


def test_calculate_user_stats_raises_error_when_question_id_does_not_exist() -> None:
    questions = [
        FakeSurveyQuestion(id=1, stat_axis=FakeStatAxis.COMBAT),
    ]

    with pytest.raises(ValueError, match="존재하지 않는 설문 문항"):
        calculate_user_stats(
            questions=questions,
            answers_by_question_id={999: 2},
        )
