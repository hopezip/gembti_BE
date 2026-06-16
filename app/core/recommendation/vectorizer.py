from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.core.recommendation.trait_mapper import map_game_traits

if TYPE_CHECKING:
    from app.stat.models import UserStats

# 다중 장르 게임의 벡터가 6축에 고르게 퍼져 변별력이 떨어지는 것을 막기 위한
# 대비(contrast) 지수. 정규화 전에 각 축을 거듭제곱해 주성향을 도드라지게 한다.
# 단조 변환이므로 최고 성향 축(순위)은 그대로 유지되고, 게임 간 변별력만 높아진다.
_CONTRAST_EXPONENT = 2.0


def game_to_vector(genres: list[str], categories: list[str]) -> list[float]:
    """게임 장르·카테고리를 L2 정규화된 6대 성향 단위 벡터로 변환한다.

    반환값 순서: [combat, strategy, cooperation, exploration, growth, healing]
    """
    vector = [0.0] * 6
    for importance, traits in map_game_traits(genres, categories):
        for i, t in enumerate(traits):
            vector[i] += importance * t
    vector = [value**_CONTRAST_EXPONENT for value in vector]
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
