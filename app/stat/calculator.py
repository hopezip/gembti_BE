# 설문 응답 점수 정규화 및 6대 성향 계산
from __future__ import annotations

from typing import Any

AXES = ("combat", "strategy", "cooperation", "exploration", "growth", "healing")


def normalize_score(raw_score: int, question_count: int) -> int:
    if question_count == 0:
        return 50

    min_score = question_count * -2
    max_score = question_count * 2
    score_range = max_score - min_score

    if score_range == 0:
        return 50

    normalized = ((raw_score - min_score) / score_range) * 100
    return round(normalized)


def calculate_user_stats(
    questions: list[Any],
    answers_by_question_id: dict[int, int | None],
) -> dict[str, int]:
    raw_scores = dict.fromkeys(AXES, 0)
    counts = dict.fromkeys(AXES, 0)

    question_by_id = {question.id: question for question in questions}

    for question_id, answer_score in answers_by_question_id.items():
        if answer_score is None:
            continue

        question = question_by_id.get(question_id)
        if question is None:
            raise ValueError("존재하지 않는 설문 문항 응답입니다.")

        axis = question.stat_axis.value

        raw_scores[axis] += answer_score
        counts[axis] += 1

    return {axis: normalize_score(raw_scores[axis], counts[axis]) for axis in AXES}
