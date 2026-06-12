"""고객센터 ``chat_chunk`` 벡터 RAG용 임베딩 경계 모듈."""

from __future__ import annotations

import hashlib
import importlib
import math
import os
from typing import Any, Protocol

CHAT_CHUNK_EMBEDDING_DIMENSIONS = 1536
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_API_KEY = "OPENAI_API_KEY"
SUPPORT_CHAT_EMBEDDING_MODEL_ENV = "SUPPORT_CHAT_EMBEDDING_MODEL"
SUPPORT_CHAT_EMBEDDING_DIMENSIONS_ENV = "SUPPORT_CHAT_EMBEDDING_DIMENSIONS"


class EmbeddingClient(Protocol):
    def embed_text(self, text: str) -> list[float]:
        """주어진 텍스트의 임베딩 벡터를 반환한다."""


class EmbeddingConfigurationError(RuntimeError):
    """실제 임베딩 클라이언트를 구성할 수 없을 때 발생한다."""


class EmbeddingResponseError(RuntimeError):
    """임베딩 벡터가 없거나, 형식이 잘못되었거나, 차원이 맞지 않을 때 발생한다."""


def validate_embedding_dimensions(
    vector,
    *,
    expected_dimensions: int = CHAT_CHUNK_EMBEDDING_DIMENSIONS,
) -> list[float]:
    """유한한 숫자 값과 고정 ``chat_chunk`` 차원을 검증한다."""

    try:
        normalized = [float(value) for value in vector]
    except (TypeError, ValueError) as exc:
        raise EmbeddingResponseError("embedding vector must contain numeric values") from exc
    if len(normalized) != expected_dimensions:
        raise EmbeddingResponseError(
            f"embedding vector expected {expected_dimensions} dimensions, got {len(normalized)}"
        )
    if any(not math.isfinite(value) for value in normalized):
        raise EmbeddingResponseError("embedding vector contained non-finite values")
    return normalized


def _validate_model_name(model: str) -> str:
    normalized_model = model.strip()
    if not normalized_model:
        raise EmbeddingConfigurationError("embedding model must not be blank")
    return normalized_model


def _validate_optional_dimensions(dimensions: int | None) -> int | None:
    if dimensions is None:
        return None
    if dimensions <= 0:
        raise EmbeddingConfigurationError("dimensions must be greater than 0")
    return dimensions


def _resolve_required_api_key(api_key: str | None) -> str:
    resolved_api_key = api_key or os.getenv(OPENAI_API_KEY)
    if resolved_api_key is None or not resolved_api_key.strip():
        raise EmbeddingConfigurationError(
            f"{OPENAI_API_KEY} is required to create OpenAIEmbeddingClient"
        )
    return resolved_api_key


def _parse_optional_positive_int(raw_value: str | None, env_name: str) -> int | None:
    if raw_value is None or not raw_value.strip():
        return None
    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise EmbeddingConfigurationError(f"{env_name} must be a positive integer") from exc
    if parsed_value <= 0:
        raise EmbeddingConfigurationError(f"{env_name} must be greater than 0")
    return parsed_value


def _create_openai_client(*, api_key: str, timeout: float | None) -> Any:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise EmbeddingConfigurationError(
            "openai package is required for OpenAIEmbeddingClient"
        ) from exc

    openai_client_type = getattr(openai_module, "OpenAI", None)
    if openai_client_type is None:
        raise EmbeddingConfigurationError("openai.OpenAI is not available")

    kwargs: dict[str, Any] = {"api_key": api_key}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return openai_client_type(**kwargs)


def _extract_embedding(response: Any, *, expected_dimensions: int | None) -> list[float]:
    data = getattr(response, "data", None)
    if not data:
        raise EmbeddingResponseError("embedding response did not include data")

    raw_embedding = getattr(data[0], "embedding", None)
    if raw_embedding is None:
        raise EmbeddingResponseError("embedding response did not include an embedding")

    try:
        vector = [float(value) for value in raw_embedding]
    except (TypeError, ValueError) as exc:
        raise EmbeddingResponseError("embedding response must contain numeric values") from exc

    if not vector:
        raise EmbeddingResponseError("embedding response was empty")
    if any(not math.isfinite(value) for value in vector):
        raise EmbeddingResponseError("embedding response contained non-finite values")
    if expected_dimensions is not None and len(vector) != expected_dimensions:
        raise EmbeddingResponseError(
            f"embedding response expected {expected_dimensions} dimensions, got {len(vector)}"
        )
    return vector


class OpenAIEmbeddingClient:
    """OpenAI Embeddings API를 사용하는 런타임 임베딩 클라이언트.

    SDK는 실제 클라이언트를 만들어야 할 때만 지연 임포트된다. 테스트에서는
    ``sdk_client``를 주입해 기본 테스트 스위트가 네트워크 없이 동작하도록 한다.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        api_key: str | None = None,
        dimensions: int | None = CHAT_CHUNK_EMBEDDING_DIMENSIONS,
        sdk_client: Any | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = _validate_model_name(model)
        self.dimensions = _validate_optional_dimensions(dimensions)
        if sdk_client is None:
            sdk_client = _create_openai_client(
                api_key=_resolve_required_api_key(api_key),
                timeout=timeout,
            )
        self._client = sdk_client

    @classmethod
    def from_env(cls, *, sdk_client: Any | None = None) -> OpenAIEmbeddingClient:
        """환경 변수로 OpenAI 임베딩 클라이언트를 생성한다."""

        configured_dimensions = _parse_optional_positive_int(
            os.getenv(SUPPORT_CHAT_EMBEDDING_DIMENSIONS_ENV),
            SUPPORT_CHAT_EMBEDDING_DIMENSIONS_ENV,
        )
        return cls(
            model=os.getenv(
                SUPPORT_CHAT_EMBEDDING_MODEL_ENV,
                DEFAULT_OPENAI_EMBEDDING_MODEL,
            ),
            api_key=os.getenv(OPENAI_API_KEY),
            dimensions=configured_dimensions or CHAT_CHUNK_EMBEDDING_DIMENSIONS,
            sdk_client=sdk_client,
        )

    def embed_text(self, text: str) -> list[float]:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("text must not be blank")

        request: dict[str, Any] = {
            "model": self.model,
            "input": normalized_text,
            "encoding_format": "float",
        }
        if self.dimensions is not None:
            request["dimensions"] = self.dimensions

        response = self._client.embeddings.create(**request)
        return _extract_embedding(response, expected_dimensions=self.dimensions)


class FakeEmbeddingClient:
    """테스트용 결정론적·네트워크 비의존 임베딩 클라이언트."""

    def __init__(self, dimensions: int = CHAT_CHUNK_EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than 0")
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        normalized_text = text.strip()
        if not normalized_text:
            return [0.0] * self.dimensions
        return [
            self._value_for_dimension(normalized_text, index) for index in range(self.dimensions)
        ]

    @staticmethod
    def _value_for_dimension(text: str, index: int) -> float:
        digest = hashlib.blake2b(
            f"{index}\0{text}".encode(),
            digest_size=8,
            person=b"chatfake",
        ).digest()
        raw_value = int.from_bytes(digest, byteorder="big", signed=False)
        return (raw_value / ((1 << 64) - 1)) * 2.0 - 1.0


__all__ = [
    "CHAT_CHUNK_EMBEDDING_DIMENSIONS",
    "DEFAULT_OPENAI_EMBEDDING_MODEL",
    "EmbeddingClient",
    "EmbeddingConfigurationError",
    "EmbeddingResponseError",
    "FakeEmbeddingClient",
    "OpenAIEmbeddingClient",
    "validate_embedding_dimensions",
]
