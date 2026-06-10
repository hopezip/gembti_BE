from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def cosine_similarity(
    left_vector: Sequence[float],
    right_vector: Sequence[float],
) -> float:
    """두 벡터의 코사인 유사도를 계산한다.

    vectorizer에서 이미 L2 정규화된 단위 벡터를 반환하므로,
    같은 차원의 벡터끼리는 내적값이 코사인 유사도가 된다.
    """
    if len(left_vector) != len(right_vector):
        raise ValueError("두 벡터의 차원이 같아야 합니다.")

    return sum(
        left_value * right_value
        for left_value, right_value in zip(left_vector, right_vector, strict=True)
    )
