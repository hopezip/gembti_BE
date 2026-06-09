# survey Request/Response 스키마
from pydantic import BaseModel, Field


class SurveyQuestionResponse(BaseModel):
    question_id: int
    question_text: str
    stat_axis: str
    display_order: int


class SurveyAnswerRequest(BaseModel):
    question_id: int = Field(
        ...,
        ge=1,
        examples=[1],
    )
    answer: int = Field(
        ...,
        ge=-2,
        le=2,
        examples=[2],
    )


class SurveySubmitRequest(BaseModel):
    answers: list[SurveyAnswerRequest] = Field(
        ...,
        examples=[
            [
                {"question_id": 1, "answer": 2},
                {"question_id": 2, "answer": 1},
                {"question_id": 3, "answer": 0},
            ]
        ],
    )


class SurveySubmitResponse(BaseModel):
    user_stats_id: int
    stats: dict[str, int]
    source_type: str
    survey_mode: str
