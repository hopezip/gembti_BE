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


def calculate_steam_stats_from_vectors(vectors: list[list[float]]) -> dict[str, int] | None:
    if not vectors:
        return None

    axis_totals = dict.fromkeys(AXES, 0.0)

    for vector in vectors:
        for index, axis in enumerate(AXES):
            axis_totals[axis] += float(vector[index])

    axis_averages = {axis: axis_totals[axis] / len(vectors) for axis in AXES}

    max_score = max(axis_averages.values())
    if max_score <= 0:
        return dict.fromkeys(AXES, 50)

    return {axis: round((axis_averages[axis] / max_score) * 100) for axis in AXES}


def merge_survey_and_steam_stats(
    survey_stats: dict[str, int],
    steam_stats: dict[str, int],
    survey_weight: float = 0.5,
    steam_weight: float = 0.5,
) -> dict[str, int]:
    return {
        axis: round((survey_stats[axis] * survey_weight) + (steam_stats[axis] * steam_weight))
        for axis in AXES
    }
