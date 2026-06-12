from dataclasses import dataclass
import json
from typing import Any, cast
from uuid import uuid4

from app.chat.infrastructure.llm import FALLBACK_ANSWER
from app.chat.schemas import (
    SupportChatCitation,
    SupportChatFinalPayload,
    SupportChatMessageRequest,
)
from app.core.config import settings
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
    redis = cast("Any", await get_redis())

    await redis.hset(key, mapping={"turn_count": "0"})
    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)

    return session_id


async def refresh_support_chat_session_ttl(session_id: str) -> bool:
    key = support_chat_session_key(session_id)
    redis = cast("Any", await get_redis())

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
    redis = cast("Any", await get_redis())
    turn = json.dumps(
        {"user": user_message, "assistant": assistant_answer},
        ensure_ascii=False,
    )

    await redis.rpush(key, turn)
    await redis.ltrim(key, -3, -1)
    await redis.expire(key, settings.SUPPORT_CHAT_SESSION_TTL_SECONDS)


async def get_recent_support_chat_turns(session_id: str) -> list[dict[str, str]]:
    key = support_chat_session_turns_key(session_id)
    redis = cast("Any", await get_redis())
    turns = await redis.lrange(key, 0, -1)
    decoded_turns = [
        json.loads(turn.decode("utf-8") if isinstance(turn, bytes) else turn) for turn in turns
    ]
    return decoded_turns


def build_support_chat_question(
    message: str,
    recent_turns: list[dict[str, str]],
) -> str:
    if not recent_turns:
        return message

    turn_lines = []
    for turn in recent_turns[-3:]:
        user_message = turn.get("user", "").strip()
        assistant_answer = turn.get("assistant", "").strip()
        if user_message:
            turn_lines.append(f"사용자: {user_message}")
        if assistant_answer:
            turn_lines.append(f"챗봇: {assistant_answer}")

    if not turn_lines:
        return message

    return "\n".join(
        [
            "최근 대화:",
            *turn_lines,
            "",
            "현재 질문:",
            message,
        ]
    )


def validate_support_chat_message_request(request: SupportChatMessageRequest) -> None:
    if not request.message:
        raise BadRequestException("메시지는 필수입니다.")
    if request.session_id is not None and not request.session_id:
        raise BadRequestException("session_id 형식이 올바르지 않습니다.")


@dataclass(frozen=True)
class SupportChatAnswer:
    answer: str
    citations: list[SupportChatCitation]
    fallback_used: bool


async def generate_support_chat_answer(
    message: str,
    recent_turns: list[dict[str, str]],
) -> SupportChatAnswer:
    # PR 1에서는 세션/API 계약만 고정한다.
    # 실제 RAG 답변 생성은 후속 PR에서 이 함수 내부 구현만 교체한다.
    _ = build_support_chat_question(message, recent_turns)
    return SupportChatAnswer(
        answer=FALLBACK_ANSWER,
        citations=[],
        fallback_used=True,
    )


async def create_support_chat_message(
    request: SupportChatMessageRequest,
) -> SupportChatFinalPayload:
    validate_support_chat_message_request(request)
    session_expired = False
    if request.session_id is None:
        session_id = await create_support_chat_session()
    elif await refresh_support_chat_session_ttl(request.session_id):
        session_id = request.session_id
    else:
        session_id = await create_support_chat_session()
        session_expired = True

    recent_turns = await get_recent_support_chat_turns(session_id)
    answer_result = await generate_support_chat_answer(
        message=request.message,
        recent_turns=recent_turns,
    )
    if isinstance(answer_result, str):
        answer = answer_result
        citations = []
        fallback_used = True
    else:
        answer = answer_result.answer
        citations = answer_result.citations
        fallback_used = answer_result.fallback_used

    await save_support_chat_turn(
        session_id=session_id,
        user_message=request.message,
        assistant_answer=answer,
    )

    return SupportChatFinalPayload(
        session_id=session_id,
        answer=answer,
        citations=citations,
        fallback_used=fallback_used,
        session_expired=session_expired,
    )
