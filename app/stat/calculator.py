# 설문 응답 점수 정규화 및 6대 성향 계산
from app.survey.models import SurveyQuestion

AXES = ("combat", "strategy", "cooperation", "exploration", "growth", "healing")


def normalize_score(raw_score: int, question_count: int) -> int:
    if question_count == 0:
        return 50

    min_score = question_count * -2
    max_score = question_count * 2

    normalized = ((raw_score - min_score) / (max_score - min_score)) * 100
    return round(normalized)


def calculate_user_stats(
    questions: list[SurveyQuestion],
    answers_by_question_id: dict[int, int],
) -> dict[str, int]:
    raw_scores = dict.fromkeys(AXES, 0)
    counts = dict.fromkeys(AXES, 0)

    question_by_id = {question.id: question for question in questions}

    for question_id, answer_score in answers_by_question_id.items():
        question = question_by_id[question_id]
        axis = (
            question.stat_axis.value if hasattr(question.stat_axis, "value") else question.stat_axis
        )

        raw_scores[axis] += answer_score
        counts[axis] += 1

    return {axis: normalize_score(raw_scores[axis], counts[axis]) for axis in AXES}
