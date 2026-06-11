# survey Request/Response 스키마
from pydantic import BaseModel, ConfigDict, Field


class SurveyQuestionResponse(BaseModel):
    question_id: int
    question_text: str
    stat_axis: str
    display_order: int


class SurveyAnswerRequest(BaseModel):
    question_id: int
    answer: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="선택지 번호. 1~5 중 하나이며, 건너뛰기 시 null",
    )


class SurveySubmitRequest(BaseModel):
    answers: list[SurveyAnswerRequest]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answers": [
                    {"question_id": 1, "answer": 4},
                    {"question_id": 2, "answer": 3},
                    {"question_id": 3, "answer": None},
                ]
            }
        }
    )


class SurveySubmitResponse(BaseModel):
    user_stats_id: int
    stats: dict[str, int]
    source_type: str
    survey_mode: str


class SurveyResultResponse(BaseModel):
    user_stats_id: int
    stats: dict[str, int]
    source_type: str
    survey_mode: str | None
    created_at: str
