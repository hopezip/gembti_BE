from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from app.chat.cs import service as support_chat_service
from app.chat.schemas import (
    SupportChatHistoryResponse,
    SupportChatMessageRequest,
)
from app.core.dependencies import get_current_user_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/support/chat", tags=["Chat"])
_err = lambda msg: {"content": {"application/json": {"example": {"error": msg}}}}  # noqa: E731


@router.post(
    "/messages",
    response_model=None,
    response_class=StreamingResponse,
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
        429: _err("요청이 너무 많습니다."),
    },
)
async def stream_support_chat_message_endpoint(
    request_body: SupportChatMessageRequest,
    user_id: int = Depends(get_current_user_id),
) -> StreamingResponse:
    support_chat_service.validate_support_chat_message_request(request_body)

    session_id, session_expired = await support_chat_service.resolve_support_chat_session(
        request_body,
        user_id=user_id,
    )

    return StreamingResponse(
        _stream_support_chat_message(
            request_body,
            session_id=session_id,
            session_expired=session_expired,
        ),
        media_type="text/event-stream",
    )


@router.get(
    "/messages",
    response_model=SupportChatHistoryResponse,
    responses={
        401: _err("인증이 필요합니다."),
    },
)
async def get_support_chat_messages_endpoint(
    session_id: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
) -> SupportChatHistoryResponse:
    return await support_chat_service.get_support_chat_history(
        session_id=session_id,
        user_id=user_id,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        401: _err("인증이 필요합니다."),
        403: _err("삭제 권한 없음"),
        404: _err("존재하지 않는 세션"),
    },
)
async def delete_support_chat_session_endpoint(
    session_id: str,
    user_id: int = Depends(get_current_user_id),
) -> Response:
    await support_chat_service.delete_support_chat_session(
        session_id=session_id,
        user_id=user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _stream_support_chat_message(
    request_body: SupportChatMessageRequest,
    session_id: str,
    session_expired: bool,
) -> AsyncIterator[str]:
    try:
        async for event in support_chat_service.stream_resolved_support_chat_message(
            request_body,
            session_id=session_id,
            session_expired=session_expired,
        ):
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
