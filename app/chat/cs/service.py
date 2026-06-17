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
from app.chat.schemas import SupportChatFinalPayload, SupportChatMessageRequest
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.enums import RedisPurpose
from app.core.exceptions import BadRequestException
from app.core.redis import get_redis

SUPPORT_CHAT_SESSION_PREFIX = "support_chat:session:"


def support_chat_session_key(session_id: str) -> str:
    return f"{SUPPORT_CHAT_SESSION_PREFIX}{session_id}"


def support_chat_session_turns_key(session_id: str) -> str:
    return f"{support_chat_session_key(session_id)}:turns"


async def create_support_chat_session() -> str:
    session_id = str(uuid4())
    key = support_chat_session_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))

    await redis.hset(key, mapping={"turn_count": "0"})
    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)

    return session_id


async def refresh_support_chat_session_ttl(session_id: str) -> bool:
    key = support_chat_session_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))

    if not await redis.exists(key):
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
    await redis.ltrim(key, -3, -1)
    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)


async def get_recent_support_chat_turns(session_id: str) -> list[dict[str, str]]:
    key = support_chat_session_turns_key(session_id)
    redis = cast("Any", await get_redis(RedisPurpose.SUPPORT))
    turns = await redis.lrange(key, 0, -1)
    decoded_turns = [
        json.loads(turn.decode("utf-8") if isinstance(turn, bytes) else turn) for turn in turns
    ]
    return decoded_turns


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


async def _resolve_support_chat_session(
    request: SupportChatMessageRequest,
) -> tuple[str, bool]:
    if request.session_id is None:
        return await create_support_chat_session(), False
    if await refresh_support_chat_session_ttl(request.session_id):
        return request.session_id, False
    return await create_support_chat_session(), True


async def stream_support_chat_message(
    request: SupportChatMessageRequest,
) -> AsyncIterator[dict[str, object]]:
    validate_support_chat_message_request(request)
    session_id, session_expired = await _resolve_support_chat_session(request)

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
