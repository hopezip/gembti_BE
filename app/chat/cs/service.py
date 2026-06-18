from collections.abc import AsyncIterator
import json
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.chat.infrastructure.embedding import (
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    OpenAIEmbeddingClient,
)
from app.chat.infrastructure.llm import (
    FALLBACK_ANSWER,
    LlmConfigurationError,
    LlmResponseError,
    OpenAIChatResponder,
    iter_text_deltas,
)
from app.chat.infrastructure.vector_store import AsyncPgvectorChatChunkVectorStore
from app.chat.rag.model import SUPPORT_RAG_SETTINGS
from app.chat.rag.service import (
    SupportRagAnswer,
    SupportRagAnswerDelta,
    SupportRagAnswerFinal,
    stream_support_rag_answer,
)
from app.chat.schemas import (
    SupportChatFinalPayload,
    SupportChatHistoryMessage,
    SupportChatHistoryResponse,
    SupportChatMessageRequest,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.enums import RedisPurpose
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.redis import get_redis

SUPPORT_CHAT_SESSION_PREFIX = "support_chat:session:"


def support_chat_session_key(session_id: str) -> str:
    return f"{SUPPORT_CHAT_SESSION_PREFIX}{session_id}"


def support_chat_session_turns_key(session_id: str) -> str:
    return f"{support_chat_session_key(session_id)}:turns"


async def create_support_chat_session(user_id: int) -> str:
    session_id = str(uuid4())
    key = support_chat_session_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))

    await redis.hset(
        key,
        mapping={
            "user_id": str(user_id),
            "turn_count": "0",
        },
    )

    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)

    return session_id


def validate_support_chat_session_owner(
    session: dict[str, str],
    user_id: int,
) -> bool:
    owner_user_id = session.get("user_id")
    if owner_user_id is None:
        return False

    return owner_user_id == str(user_id)


async def refresh_support_chat_session_ttl(session_id: str, user_id: int) -> bool:
    key = support_chat_session_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))

    session = await redis.hgetall(key)
    if not session:
        return False

    if not validate_support_chat_session_owner(session, user_id=user_id):
        return False

    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)
    return True


async def save_support_chat_turn(
    session_id: str,
    user_message: str,
    assistant_answer: str,
) -> None:
    key = support_chat_session_turns_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))
    turn = json.dumps(
        {"user": user_message, "assistant": assistant_answer},
        ensure_ascii=False,
    )

    await redis.rpush(key, turn)
    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)


async def get_recent_support_chat_turns(session_id: str) -> list[dict[str, str]]:
    key = support_chat_session_turns_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))
    turns = await redis.lrange(key, -3, -1)
    decoded_turns = [_decode_support_chat_turn(turn) for turn in turns]
    return decoded_turns


def _decode_support_chat_turn(turn: str | bytes) -> dict[str, str]:
    raw_turn = turn.decode("utf-8") if isinstance(turn, bytes) else turn
    return cast("dict[str, str]", json.loads(raw_turn))


async def get_support_chat_history(
    session_id: str | None,
    user_id: int,
) -> SupportChatHistoryResponse:
    if session_id is None:
        return SupportChatHistoryResponse(session_id=None, results=[])

    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        return SupportChatHistoryResponse(session_id=None, results=[])

    session_key = support_chat_session_key(normalized_session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))
    session = await redis.hgetall(session_key)
    if not session:
        return SupportChatHistoryResponse(session_id=None, results=[])

    if not validate_support_chat_session_owner(session, user_id=user_id):
        return SupportChatHistoryResponse(session_id=None, results=[])

    turns_key = support_chat_session_turns_key(normalized_session_id)
    turns = await redis.lrange(turns_key, 0, -1)
    results: list[SupportChatHistoryMessage] = []
    for turn in turns:
        decoded_turn = _decode_support_chat_turn(turn)
        results.append(SupportChatHistoryMessage(role="user", message=decoded_turn["user"]))
        results.append(
            SupportChatHistoryMessage(
                role="assistant",
                message=decoded_turn["assistant"],
            )
        )

    return SupportChatHistoryResponse(
        session_id=normalized_session_id,
        results=results,
    )


async def delete_support_chat_session(session_id: str, user_id: int) -> None:
    session_key = support_chat_session_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))
    session = await redis.hgetall(session_key)
    if not session:
        raise NotFoundException("존재하지 않는 세션")

    if not validate_support_chat_session_owner(session, user_id=user_id):
        raise ForbiddenException("삭제 권한 없음")

    await redis.delete(session_key, support_chat_session_turns_key(session_id))


def validate_support_chat_message_request(request: SupportChatMessageRequest) -> None:
    if not request.message:
        raise BadRequestException("메시지는 필수입니다.")
    if request.session_id is not None and not request.session_id:
        raise BadRequestException("session_id 형식이 올바르지 않습니다.")


async def stream_support_chat_answer(
    message: str,
    recent_turns: list[dict[str, str]],
) -> AsyncIterator[SupportRagAnswerDelta | SupportRagAnswerFinal]:
    try:
        async with AsyncSessionLocal() as db:
            async for event in stream_support_rag_answer(
                message=message,
                recent_turns=recent_turns,
                embedding_client=OpenAIEmbeddingClient.from_env(),
                vector_store=AsyncPgvectorChatChunkVectorStore(
                    db,
                    score_threshold=SUPPORT_RAG_SETTINGS.score_threshold,
                ),
                responder=OpenAIChatResponder.from_env(),
            ):
                yield event
    except (
        EmbeddingConfigurationError,
        EmbeddingResponseError,
        LlmConfigurationError,
        LlmResponseError,
        SQLAlchemyError,
        ValueError,
    ):
        answer_deltas: list[str] = []
        for delta in iter_text_deltas(FALLBACK_ANSWER):
            answer_deltas.append(delta)
            yield SupportRagAnswerDelta(content=delta)

        yield SupportRagAnswerFinal(
            answer=SupportRagAnswer(
                answer="".join(answer_deltas),
                citations=[],
                fallback_used=True,
            )
        )


async def resolve_support_chat_session(
    request: SupportChatMessageRequest,
    user_id: int,
) -> tuple[str, bool]:
    if request.session_id is None:
        return await create_support_chat_session(user_id=user_id), False
    if await refresh_support_chat_session_ttl(request.session_id, user_id=user_id):
        return request.session_id, False
    return await create_support_chat_session(user_id=user_id), True


async def stream_resolved_support_chat_message(
    request: SupportChatMessageRequest,
    session_id: str,
    session_expired: bool,
) -> AsyncIterator[dict[str, object]]:
    recent_turns = await get_recent_support_chat_turns(session_id)
    async for event in stream_support_chat_answer(
        message=request.message,
        recent_turns=recent_turns,
    ):
        if isinstance(event, SupportRagAnswerDelta):
            if event.content:
                yield {"type": "delta", "content": event.content}
            continue

        answer_result = event.answer
        await save_support_chat_turn(
            session_id=session_id,
            user_message=request.message,
            assistant_answer=answer_result.answer,
        )
        final_payload = SupportChatFinalPayload(
            session_id=session_id,
            answer=answer_result.answer,
            citations=answer_result.citations,
            fallback_used=answer_result.fallback_used,
            session_expired=session_expired,
        )
        final_event = final_payload.model_dump(exclude_none=True)
        final_event["type"] = "final"
        yield final_event


async def stream_support_chat_message(
    request: SupportChatMessageRequest,
    user_id: int,
) -> AsyncIterator[dict[str, object]]:
    validate_support_chat_message_request(request)
    session_id, session_expired = await resolve_support_chat_session(request, user_id=user_id)

    async for event in stream_resolved_support_chat_message(
        request,
        session_id=session_id,
        session_expired=session_expired,
    ):
        yield event
