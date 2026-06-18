from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class SupportChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class SupportChatCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int
    title: str
    chunk_id: int
    similarity: float


class SupportChatFinalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    answer: str
    citations: list[SupportChatCitation]
    fallback_used: bool
    session_expired: bool = False
    suggested_next_steps: list[str] | None = None


class SupportChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    message: str


class SupportChatHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None
    results: list[SupportChatHistoryMessage]
