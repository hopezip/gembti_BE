from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.recommendation.vectorizer import game_to_vector, user_stats_to_vector
from app.stat.models import StatSourceType, SurveyMode, UserStats

_COMBAT, _STRATEGY = 0, 1


def _dominant_axis(vector: list[float]) -> int:
    return vector.index(max(vector))


def test_user_stats_to_vector_returns_unit_vector() -> None:
    stats = UserStats(
        user_id=1,
        combat=100,
        strategy=0,
        cooperation=0,
        exploration=0,
        growth=0,
        healing=0,
        source_type=StatSourceType.ONLY_SURVEY,
        survey_mode=SurveyMode.STANDARD,
        negative_tags=[],
    )

    vector = user_stats_to_vector(stats)

    assert vector == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_game_to_vector_returns_six_dimension_vector() -> None:
    vector = game_to_vector(genres=["Action", "RPG"], categories=["Co-op"])

    assert len(vector) == 6


def test_game_to_vector_returns_unit_vector() -> None:
    vector = game_to_vector(genres=["Action", "RPG"], categories=["Co-op"])
    norm = sum(value * value for value in vector) ** 0.5

    assert norm == pytest.approx(1.0)


def test_game_to_vector_returns_fallback_unit_vector_when_no_mapping_exists() -> None:
    vector = game_to_vector(genres=["Unknown Genre"], categories=["Unknown Category"])
    norm = sum(value * value for value in vector) ** 0.5

    assert len(vector) == 6
    assert norm == pytest.approx(1.0)


def test_game_to_vector_dominant_axis_follows_primary_genre() -> None:
    action_first = game_to_vector(genres=["Action", "Indie"], categories=["Single-player"])
    strategy_first = game_to_vector(genres=["Strategy", "Indie"], categories=["Single-player"])

    assert _dominant_axis(action_first) == _COMBAT
    assert _dominant_axis(strategy_first) == _STRATEGY


def test_game_to_vector_is_sensitive_to_genre_order() -> None:
    action_primary = game_to_vector(
        genres=["Action", "Strategy", "Indie"], categories=["Single-player"]
    )
    strategy_primary = game_to_vector(
        genres=["Strategy", "Action", "Indie"], categories=["Single-player"]
    )

    assert action_primary != strategy_primary
    assert _dominant_axis(action_primary) == _COMBAT
    assert _dominant_axis(strategy_primary) == _STRATEGY


def test_game_to_vector_contrast_keeps_dominant_axis_sharp() -> None:
    vector = game_to_vector(genres=["Action", "RPG", "Indie"], categories=["Single-player", "PvP"])
    mean = sum(vector) / len(vector)

    assert _dominant_axis(vector) == _COMBAT
    assert vector[_COMBAT] > mean * 2
