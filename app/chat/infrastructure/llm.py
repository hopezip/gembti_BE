from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING, Any, Protocol

from app.chat.cs.prompt import SUPPORT_ANSWER_POLICY, SUPPORT_ANSWER_USER_PROMPT_TEMPLATE

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    class ChatChunkHit(Protocol):
        @property
        def source(self) -> str: ...

        @property
        def content(self) -> str: ...


FALLBACK_ANSWER = (
    "근거 문서에서 확인되지 않아 일반 안내만 제공할 수 있어요. "
    "질문을 조금 더 구체적으로 바꾸거나 운영팀에 문의해 주세요."
)

SUPPORT_CHAT_LLM_MODEL_ENV = "SUPPORT_CHAT_LLM_MODEL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini"


class LlmConfigurationError(RuntimeError):
    pass


class LlmResponseError(RuntimeError):
    pass


class SupportResponder(Protocol):
    def stream_answer(
        self,
        question: str,
        chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...],
        recent_turns: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]: ...


class DeterministicSupportResponder:
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
        recent_turns: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        del recent_turns
        for delta in iter_text_deltas(self.answer(question, chunks)):
            yield delta


class OpenAIChatResponder:
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
        return cls(
            model=os.getenv(SUPPORT_CHAT_LLM_MODEL_ENV, DEFAULT_OPENAI_CHAT_MODEL),
            api_key=_load_openai_api_key_from_settings(),
            sdk_client=sdk_client,
        )

    async def stream_answer(
        self,
        question: str,
        chunks: list[ChatChunkHit] | tuple[ChatChunkHit, ...],
        recent_turns: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        if not chunks:
            for delta in iter_text_deltas(FALLBACK_ANSWER):
                yield delta
            return

        messages = _build_chat_messages(question, chunks, recent_turns=recent_turns)
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
    recent_turns: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    context = "\n\n".join(
        f"[참고 문서 {index}] {chunk.content}"
        for index, chunk in enumerate(chunks[:3], start=1)
        if chunk.content.strip()
    )
    messages = [
        {
            "role": "system",
            "content": SUPPORT_ANSWER_POLICY,
        }
    ]
    for turn in recent_turns or []:
        user_message = turn.get("user", "").strip()
        assistant_answer = turn.get("assistant", "").strip()
        if user_message:
            messages.append({"role": "user", "content": user_message})
        if assistant_answer:
            messages.append({"role": "assistant", "content": assistant_answer})

    messages.append(
        {
            "role": "user",
            "content": SUPPORT_ANSWER_USER_PROMPT_TEMPLATE.format(
                retrieved_chunks=context,
                user_query=question,
            ),
        }
    )

    return messages


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
