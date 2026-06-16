from pydantic import ValidationError
import pytest

from app.chat.schemas import SupportChatFinalPayload, SupportChatMessageRequest


def test_support_chat_message_request_strips_message() -> None:
    request = SupportChatMessageRequest(message="  Steam 연동이 안되는데   ")

    assert request.message == "Steam 연동이 안되는데"
    assert request.session_id is None


def test_support_chat_message_request_strips_session_id() -> None:
    request = SupportChatMessageRequest(message="후속 질문", session_id=" abc-123 ")

    assert request.session_id == "abc-123"


def test_support_chat_message_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SupportChatMessageRequest(
            message="비정상 필드",
            category_hint="steam",
        )


def test_support_chat_final_payload_accepts_citations() -> None:
    payload = SupportChatFinalPayload(
        session_id="abc-123",
        answer="steam 연동은 프로필 공개 범위를 확인해 주세요.",
        citations=[
            {
                "document_id": 1,
                "title": "steam 연동 도움말",
                "chunk_id": 17,
                "similarity": 0.99,
            }
        ],
        fallback_used=False,
    )

    assert payload.answer == "steam 연동은 프로필 공개 범위를 확인해 주세요."
    assert payload.session_expired is False
    assert payload.suggested_next_steps is None
    assert payload.citations[0].title == "steam 연동 도움말"


def test_support_chat_final_payload_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SupportChatFinalPayload(
            session_id="abc-123",
            answer="답변",
            citations=[],
            fallback_used=False,
            debug_prompt="내부 프롬프트",
        )


def test_support_chat_final_payload_accepts_suggested_next_steps() -> None:
    payload = SupportChatFinalPayload(
        session_id="abc-123",
        answer="근거 문서에서 확인되지 않았어요.",
        citations=[],
        fallback_used=True,
        suggested_next_steps=["질문을 더 구체적으로 작성해 주세요."],
    )

    assert payload.fallback_used is True
    assert payload.suggested_next_steps == ["질문을 더 구체적으로 작성해 주세요."]


def test_support_chat_final_payload_can_exclude_none_fields() -> None:
    payload = SupportChatFinalPayload(
        session_id="abc-123",
        answer="답변",
        citations=[],
        fallback_used=False,
    )

    dumped = payload.model_dump(exclude_none=True)
    assert "suggested_next_steps" not in dumped
