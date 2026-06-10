from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    class ChatChunkHit(Protocol):
        """``rag.model`` merge 전까지 mypy용 최소 히트 Protocol."""

        source: str
        content: str


# ``cs.prompt`` merge 전 임시 상수. 이후 ``from app.chat.cs.prompt import ...`` 로 교체.
FALLBACK_ANSWER = (
    "근거 문서에서 확인되지 않아 일반 안내만 제공할 수 있어요. "
    "질문을 조금 더 구체적으로 바꾸거나 운영팀에 문의해 주세요."
)
SUPPORT_ANSWER_POLICY = """
고객센터 답변 정책

답변 기준
- 이 프롬프트는 고객센터 챗봇 전용이다. 설문 챗봇 플로우를 실행하거나
  성향 질문, 게임 추천 설문, 통계 산출 단계로 사용자를 유도하지 않는다.
- 답변은 이미 검색된 근거 문서 내용만 사용한다. 근거 문서에 없는 절차,
  정책, 내부 상태를 추측해서 만들지 않는다.
- 내부 시스템, 관리자 화면, 계정 상태, 결제/환불 처리 상태를 확인했다고
  말하지 않는다. 예: "계정 상태를 확인했습니다", "처리되었습니다"처럼
  실제 조회나 처리를 암시하는 문장을 금지한다.
- 근거가 부족하면 FALLBACK_ANSWER를 사용해 근거 문서가 충분하지 않음을
  사용자에게 알린다.

사용자가 해야 할 일
- suggested_next_steps는 사용자가 지금 할 수 있는 사용자 행동 문장만 담는다.
- suggested_next_steps에 개발자 TODO, 백엔드 구현 과제, 운영 로그 확인 같은
  내부 작업 지시를 넣지 않는다.

상담/운영팀으로 넘겨야 하는 경우
- 계정별 조회, 결제 처리, 환불 승인, 제재/복구 판단처럼 근거 문서만으로
  답할 수 없는 요청은 고객센터 또는 운영팀 문의로 안내한다.
""".strip()

SUPPORT_CHAT_LLM_MODEL_ENV = "SUPPORT_CHAT_LLM_MODEL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini"


class LlmConfigurationError(RuntimeError):
    """런타임 LLM 어댑터를 설정할 수 없을 때 발생한다."""


class LlmResponseError(RuntimeError):
    """런타임 LLM 응답을 읽을 수 없을 때 발생한다."""


class SupportResponder(Protocol):
    """벡터 검색 결과를 받아 답변 토큰을 스트리밍하는 인터페이스."""

    def stream_answer(
        self,
        question: str,
        chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...],
    ) -> AsyncIterator[str]:
        """이미 검색된 벡터 히트로부터 답변 토큰 조각을 순서대로 내보낸다."""


class DeterministicSupportResponder:
    """실시간 LLM 호출 없이 검색된 히트 내용으로 답변을 구성한다."""

    def answer(self, question: str, chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...]) -> str:
        del question
        contents = [chunk.content.strip() for chunk in chunks[:2] if chunk.content.strip()]
        if not contents:
            return FALLBACK_ANSWER
        return "지원 문서 기준으로는 " + " ".join(contents)

    async def stream_answer(
        self,
        question: str,
        chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...],
    ) -> AsyncIterator[str]:
        for delta in iter_text_deltas(self.answer(question, chunks)):
            yield delta


class OpenAIChatResponder:
    """주입 가능한 OpenAI 채팅 어댑터. 기본값으로는 자동 생성되지 않는다."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_OPENAI_CHAT_MODEL,
        api_key: str | None = None,
        sdk_client: Any | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = _validate_model_name(model)
        if sdk_client is None:
            sdk_client = _create_async_openai_client(
                api_key=_resolve_required_api_key(api_key),
                timeout=timeout,
            )
        self._client = sdk_client

    @classmethod
    def from_env(cls, *, sdk_client: Any | None = None) -> OpenAIChatResponder:
        """환경 변수에서 모델명·API 키를 읽어 OpenAI 채팅 응답기를 만든다."""
        return cls(
            model=os.getenv(SUPPORT_CHAT_LLM_MODEL_ENV, DEFAULT_OPENAI_CHAT_MODEL),
            api_key=_load_openai_api_key_from_settings(),
            sdk_client=sdk_client,
        )

    async def stream_answer(
        self,
        question: str,
        chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...],
    ) -> AsyncIterator[str]:
        if not chunks:
            for delta in iter_text_deltas(FALLBACK_ANSWER):
                yield delta
            return

        messages = _build_chat_messages(question, chunks)
        authentication_error, api_error = _load_openai_api_exception_types()
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                stream=True,
            )
        except authentication_error as exc:
            raise LlmConfigurationError("openai authentication failed") from exc
        except api_error as exc:
            raise LlmResponseError("chat completion request failed") from exc

        saw_content = False
        try:
            async for chunk in stream:
                stream_delta = _extract_stream_delta(chunk)
                if not stream_delta:
                    continue
                saw_content = True
                yield stream_delta
        except authentication_error as exc:
            raise LlmConfigurationError("openai authentication failed") from exc
        except api_error as exc:
            raise LlmResponseError("chat completion request failed") from exc

        if not saw_content:
            for delta in iter_text_deltas(FALLBACK_ANSWER):
                yield delta


def iter_text_deltas(text: str) -> Iterator[str]:
    if not text:
        yield ""
        return
    if len(text) == 1:
        yield text
        return
    midpoint = len(text) // 2
    first = text[:midpoint]
    second = text[midpoint:]
    yield first
    if second:
        yield second


def _build_chat_messages(
    question: str,
    chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...],
) -> list[dict[str, str]]:
    context = "\n\n".join(
        f"[{chunk.source}] {chunk.content}" for chunk in chunks[:3] if chunk.content.strip()
    )
    return [
        {
            "role": "system",
            "content": SUPPORT_ANSWER_POLICY,
        },
        {
            "role": "user",
            "content": f"질문: {question}\n\n근거:\n{context}",
        },
    ]


def _validate_model_name(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        raise LlmConfigurationError("chat model must not be blank")
    return normalized


def _resolve_required_api_key(api_key: str | None) -> str:
    resolved_api_key = (
        api_key or _load_openai_api_key_from_settings() or os.getenv(OPENAI_API_KEY_ENV)
    )
    if resolved_api_key is None or not resolved_api_key.strip():
        raise LlmConfigurationError(
            f"{OPENAI_API_KEY_ENV} is required to create OpenAIChatResponder"
        )
    return resolved_api_key


def _load_openai_api_key_from_settings() -> str | None:
    try:
        from app.core.config import get_settings

        return get_settings().OPENAI_API_KEY
    except (ImportError, AttributeError, RuntimeError, ValueError):
        return None


def _create_async_openai_client(*, api_key: str, timeout: float | None) -> Any:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise LlmConfigurationError("openai package is required for OpenAIChatResponder") from exc
    openai_client_type = getattr(openai_module, "AsyncOpenAI", None)
    if openai_client_type is None:
        raise LlmConfigurationError("openai.AsyncOpenAI is not available")
    kwargs: dict[str, Any] = {"api_key": api_key}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return openai_client_type(**kwargs)


def _load_openai_api_exception_types() -> tuple[type[BaseException], type[BaseException]]:
    openai_module = importlib.import_module("openai")
    authentication_error = getattr(openai_module, "AuthenticationError", None)
    api_error = getattr(openai_module, "APIError", None)
    if authentication_error is None or api_error is None:
        raise LlmConfigurationError("openai exception types are not available")
    return authentication_error, api_error


def _extract_stream_delta(chunk: Any) -> str | None:
    try:
        choices = chunk.choices
        if not choices:
            return None
        delta = choices[0].delta
        content = delta.content
    except AttributeError as exc:
        raise LlmResponseError("chat stream chunk did not include delta content") from exc
    if content is None:
        return None
    if not isinstance(content, str):
        raise LlmResponseError("chat stream chunk did not include text content")
    if not content:
        return None
    return content


__all__ = [
    "DEFAULT_OPENAI_CHAT_MODEL",
    "DeterministicSupportResponder",
    "FALLBACK_ANSWER",
    "iter_text_deltas",
    "LlmConfigurationError",
    "LlmResponseError",
    "OpenAIChatResponder",
    "SupportResponder",
]
