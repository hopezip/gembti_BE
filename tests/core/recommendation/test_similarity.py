from __future__ import annotations

import pytest

from app.core.recommendation.similarity import cosine_similarity


def test_cosine_similarity_returns_one_for_same_vectors() -> None:
    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 1.0


def test_cosine_similarity_returns_zero_for_orthogonal_vectors() -> None:
    assert cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == 0.0


def test_cosine_similarity_raises_error_when_vector_dimensions_are_different() -> None:
    with pytest.raises(ValueError, match="두 벡터의 차원이 같아야 합니다."):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])
