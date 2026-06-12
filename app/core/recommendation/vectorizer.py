from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.core.recommendation.trait_mapper import map_game_traits

if TYPE_CHECKING:
    from app.stat.models import UserStats


def game_to_vector(genres: list[str], categories: list[str]) -> list[float]:
    """게임 장르·카테고리를 L2 정규화된 6대 성향 단위 벡터로 변환한다.

    반환값 순서: [combat, strategy, cooperation, exploration, growth, healing]
    """
    vector = [0.0] * 6
    for importance, traits in map_game_traits(genres, categories):
        for i, t in enumerate(traits):
            vector[i] += importance * t
    return _normalize(vector)


def user_stats_to_vector(stats: UserStats) -> list[float]:
    """UserStats의 6대 성향 점수를 L2 정규화된 단위 벡터로 변환한다.

    반환값 순서: [combat, strategy, cooperation, exploration, growth, healing]
    """
    vector = [
        float(stats.combat),
        float(stats.strategy),
        float(stats.cooperation),
        float(stats.exploration),
        float(stats.growth),
        float(stats.healing),
    ]
    return _normalize(vector)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm < 1e-9:
        # 매핑 정보가 없는 경우 균등 단위 벡터 반환 (모든 성향에 동등한 가중치)
        size = len(vector)
        return [1.0 / math.sqrt(size)] * size
    return [v / norm for v in vector]
