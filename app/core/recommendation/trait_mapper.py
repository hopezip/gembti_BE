from __future__ import annotations

from app.core.recommendation.trait_schema import TRAIT_AXES  # noqa: F401

GENRE_WEIGHTS: dict[str, tuple[float, list[float]]] = {
    "Action": (2.0, [0.9, 0.1, 0.1, 0.2, 0.1, 0.0]),
    "Adventure": (2.0, [0.2, 0.2, 0.1, 0.8, 0.4, 0.2]),
    "RPG": (2.0, [0.3, 0.3, 0.2, 0.5, 0.8, 0.1]),
    "Strategy": (2.0, [0.1, 0.9, 0.2, 0.1, 0.2, 0.0]),
    "Simulation": (2.0, [0.0, 0.5, 0.2, 0.4, 0.3, 0.5]),
    "Casual": (2.0, [0.0, 0.2, 0.2, 0.2, 0.1, 0.9]),
    "Massively Multiplayer": (2.0, [0.3, 0.3, 0.8, 0.4, 0.7, 0.1]),
    "Sports": (1.5, [0.7, 0.2, 0.3, 0.1, 0.2, 0.1]),
    "Racing": (1.5, [0.6, 0.2, 0.2, 0.3, 0.1, 0.1]),
    "Indie": (1.0, [0.1, 0.2, 0.1, 0.5, 0.3, 0.4]),
}

CATEGORY_WEIGHTS: dict[str, tuple[float, list[float]]] = {
    "Co-op": (2.0, [0.0, 0.1, 0.9, 0.0, 0.1, 0.1]),
    "Online Co-op": (2.0, [0.0, 0.1, 0.9, 0.0, 0.1, 0.1]),
    "Multi-player": (1.5, [0.1, 0.0, 0.8, 0.0, 0.0, 0.0]),
    "PvP": (1.5, [0.6, 0.2, 0.4, 0.0, 0.0, 0.0]),
    "Online PvP": (1.5, [0.6, 0.2, 0.4, 0.0, 0.0, 0.0]),
    "Single-player": (1.0, [0.0, 0.0, 0.0, 0.1, 0.1, 0.1]),
}

# 대소문자·공백 차이에 대응하기 위한 정규화 lookup 테이블
_GENRE_LOOKUP: dict[str, tuple[float, list[float]]] = {
    k.strip().lower(): v for k, v in GENRE_WEIGHTS.items()
}
_CATEGORY_LOOKUP: dict[str, tuple[float, list[float]]] = {
    k.strip().lower(): v for k, v in CATEGORY_WEIGHTS.items()
}


def _match(
    value: str,
    lookup: dict[str, tuple[float, list[float]]],
    matched: dict[str, tuple[float, list[float]]],
) -> None:
    """정확한 매칭 → 없으면 부분 매칭 순으로 조회해 matched에 누적한다.

    matched를 dict로 관리해 동일 키의 중복 추가를 방지한다.
    """
    normalized = value.strip().lower()

    entry = lookup.get(normalized)
    if entry:
        matched[normalized] = entry
        return

    for key, val in lookup.items():
        if key in normalized:
            matched[key] = val


def map_game_traits(
    genres: list[str],
    categories: list[str],
) -> list[tuple[float, list[float]]]:
    """장르·카테고리를 매핑 테이블에서 조회해 매칭된 (importance, traits) 목록을 반환한다.

    1단계 정확한 매칭, 2단계 부분 매칭 순으로 시도한다.
    여러 장르에서 동일한 키가 매칭돼도 중복 없이 한 번만 반영된다.
    모두 매칭 실패 시 빈 리스트를 반환하며, vectorizer에서 균등 단위 벡터로 처리된다.
    """
    matched: dict[str, tuple[float, list[float]]] = {}

    for genre in genres:
        _match(genre, _GENRE_LOOKUP, matched)

    for category in categories:
        _match(category, _CATEGORY_LOOKUP, matched)

    return list(matched.values())
