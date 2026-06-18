from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.chat.cs import service as support_chat_service
from app.chat.schemas import SupportChatMessageRequest  # noqa: TC001 - FastAPI body model
from app.core.dependencies import get_current_user_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/support/chat", tags=["Chat"])
_err = lambda msg: {"content": {"application/json": {"example": {"error": msg}}}}  # noqa: E731


@router.post(
    "/messages",
    response_model=None,
    response_class=StreamingResponse,
    dependencies=[Depends(get_current_user_id)],
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                }
            },
            "description": "고객센터 챗봇 SSE 스트림(delta/final/[DONE])",
        },
        400: _err("메시지는 필수입니다."),
        401: _err("인증이 필요합니다."),
    },
)
async def stream_support_chat_message_endpoint(
    request_body: SupportChatMessageRequest,
) -> StreamingResponse:
    support_chat_service.validate_support_chat_message_request(request_body)

    return StreamingResponse(
        _stream_support_chat_message(request_body),
        media_type="text/event-stream",
    )


async def _stream_support_chat_message(
    request_body: SupportChatMessageRequest,
) -> AsyncIterator[str]:
    try:
        async for event in support_chat_service.stream_support_chat_message(request_body):
            yield _sse_data(event)
    except Exception:
        yield _sse_data(
            {
                "type": "error",
                "message": "답변 생성 중 오류가 발생했습니다.",
            }
        )
        yield "data: [DONE]\n\n"
        return

    yield "data: [DONE]\n\n"


def _sse_data(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
