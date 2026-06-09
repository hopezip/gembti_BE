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


def map_game_traits(
    genres: list[str],
    categories: list[str],
) -> list[tuple[float, list[float]]]:
    """장르·카테고리를 매핑 테이블에서 조회해 매칭된 (importance, traits) 목록을 반환한다."""
    result: list[tuple[float, list[float]]] = []

    for genre in genres:
        entry = GENRE_WEIGHTS.get(genre)
        if entry:
            result.append(entry)

    for category in categories:
        entry = CATEGORY_WEIGHTS.get(category)
        if entry:
            result.append(entry)

    return result
