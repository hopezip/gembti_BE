from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.recommendation.vectorizer import game_to_vector, user_stats_to_vector
from app.stat.models import StatSourceType, SurveyMode, UserStats


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
