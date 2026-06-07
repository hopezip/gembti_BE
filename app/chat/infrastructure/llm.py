from __future__ import annotations

import importlib
import os
from typing import Any, Protocol

SUPPORT_LLM_MODEL_ENV = "SUPPORT_CHAT_LLM_MODEL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_OPENAI_LLM_MODEL = "gpt-4o-mini"
FALLBACK_ANSWER = (
    "일반 고객지원 서비스만 제공합니다. 추가 기능은 제공하지 않습니다."
    "질문을 조금 더 구체적으로 작성해주세요"
)


class LlmConfigurationError(RuntimeError):
    """런타임 LLM 어댑터를 설정할 수 없을 때 발생한다."""


class LlmResponseError(RuntimeError):
    """런타임 LLM 응답을 읽을 수 없을 때 발생한다."""


class ChatChunkHit(Protocol):
    """검색된 chat_chunk 히트의 최소 공개 형태."""

    source: str
    content: str


class SupportResponder(Protocol):
    """벡터 검색 결과를 받아 답변을 생성하는 인터페이스."""

    def answer(self, question: str, chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...]) -> str:
        """이미 검색된 벡터 히트로부터 답변 문자열을 만든다."""


class DeterministicSupportResponder:
    """실시간 LLM 호출 없이 검색된 히트 내용으로 답변을 구성."""

    def answer(self, question: str, chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...]) -> str:
        del question
        contents = [chunk.content.strip() for chunk in chunks[:2] if chunk.content.strip()]
        if not contents:
            return FALLBACK_ANSWER

        return "문서 시준으로는 " + "\n".join(contents)


class OpenAIChatResponder:
    """주입 가능한 OpenAI 채팅 어댑터."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_OPENAI_LLM_MODEL,
        api_key: str | None = None,
        sdk_client: Any | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = _validate_model_name(model)
        if sdk_client is None:
            sdk_client = _create_openai_client(
                api_key=_resolve_required_api_key(api_key),
                timeout=timeout,
            )
        self._client = sdk_client

    @classmethod
    def from_env(cls, *, sdk_client: Any | None = None) -> OpenAIChatResponder:
        """환경 변수에서 모델명 API키를 읽어 OpenAI 채팅 응답기를 생성."""
        return cls(
            model=os.getenv(SUPPORT_LLM_MODEL_ENV, DEFAULT_OPENAI_LLM_MODEL),
            api_key=_load_openai_api_key_from_settings(),
            sdk_client=sdk_client,
        )

    def answer(self, question: str, chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...]) -> str:
        if not chunks:
            return FALLBACK_ANSWER

        context = "\n\n".join(
            f"[{chunk.source}] {chunk.content}" for chunk in chunks[:3] if chunk.content.strip()
        )

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "고객센터 답변만 작성하세요. 제공된 chat_chunk 근거 밖의 내부 상태,"
                        "계정별 조회 결과, 처리 완료 여부를 절대 추측하지 마세요."
                    ),
                },
                {
                    "role": "user",
                    "content": f"질문: {question}\n\n근거:\n{context}",
                },
            ],
            temperature=0.5,
            max_tokens=5000,
        )
        answer = _extract_chat_answer(response)
        return answer or FALLBACK_ANSWER


def _validate_model_name(model: str) -> str:
    normalized_model = model.strip()
    if not normalized_model:
        raise LlmConfigurationError("LLM model must not be blank")
    return normalized_model


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
    """앱 설정 경계를 통해 OpenAI API 키를 읽는다."""
    try:
        from app.core.config import get_settings

        return get_settings().OPENAI_API_KEY
    except (ImportError, AttributeError, RuntimeError, ValueError):
        return None


def _create_openai_client(*, api_key: str, timeout: float | None) -> Any:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise LlmConfigurationError(
            "openai package is required to create OpenAIChatResponder"
        ) from exc
    openai_client_type = getattr(openai_module, "OpenAI", None)
    if openai_client_type is None:
        raise LlmConfigurationError("openai.OpenAI is not available")
    kwargs: dict[str, Any] = {"api_key": api_key}
    if timeout is not None:
        kwargs["timeout"] = timeout

    return openai_client_type(**kwargs)


def _extract_chat_answer(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise LlmResponseError("chat completion response did not include choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str):
        raise LlmResponseError("chat response did not include text content")

    return content.strip()


__all__ = [
    "ChatChunkHit",
    "DEFAULT_OPENAI_LLM_MODEL",
    "DeterministicSupportResponder",
    "FALLBACK_ANSWER",
    "LlmConfigurationError",
    "LlmResponseError",
    "OpenAIChatResponder",
    "SupportResponder",
]
