"""app/game/service.py 단위 테스트

_parse_game_data: 순수 함수 → 외부 의존 없이 직접 테스트
fetch_and_save_games: httpx/DB mock 처리
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.game.service import _parse_game_data, fetch_and_save_games

# ── 공통 픽스처 ───────────────────────────────────────────────────────────────


def _steam_data(
    *,
    name: str = "Test Game",
    type_: str = "game",
    is_free: bool = False,
    price_final: int = 1500000,  # 15,000원 (Steam은 100배)
    price_initial: int = 1500000,
    genres: list | None = None,
    categories: list | None = None,
    required_age: int = 0,
    release_date_str: str = "Jan 1, 2020",
    supported_languages: str = "English, Korean",
    content_descriptor_ids: list[int] | None = None,
) -> dict:
    return {
        "type": type_,
        "name": name,
        "short_description": "A test game",
        "header_image": "https://cdn.steam.com/test.jpg",
        "is_free": is_free,
        "price_overview": (
            {
                "final": price_final,
                "initial": price_initial,
            }
            if not is_free
            else {}
        ),
        "genres": genres or [{"id": "1", "description": "Action"}],
        "categories": categories or [{"id": "2", "description": "Single-player"}],
        "required_age": required_age,
        "release_date": {"coming_soon": False, "date": release_date_str},
        "supported_languages": supported_languages,
        "content_descriptors": {"ids": content_descriptor_ids or []},
    }


def _reviews(total: int = 1000, positive: int = 900) -> dict:
    return {
        "total_reviews": total,
        "total_positive": positive,
        "total_negative": total - positive,
    }


# ── _parse_game_data ──────────────────────────────────────────────────────────


def test_parse_game_data_paid_game():
    """유료 게임: price_krw = final // 100."""
    result = _parse_game_data(730, _steam_data(price_final=1500000), None, None)

    assert result["app_id"] == 730
    assert result["title"] == "Test Game"
    assert result["price_krw"] == 15000
    assert result["is_free"] is False
    assert result["is_active"] is True


def test_parse_game_data_free_game():
    """무료 게임: price_krw=0, is_free=True."""
    result = _parse_game_data(570, _steam_data(is_free=True), None, None)

    assert result["price_krw"] == 0
    assert result["is_free"] is True


def test_parse_game_data_adult_content_inactive():
    """성인 게임(required_age=18): is_active=False."""
    result = _parse_game_data(99, _steam_data(required_age=18), None, None)

    assert result["is_active"] is False


def test_parse_game_data_adult_by_content_descriptor_inactive():
    """required_age=0이어도 성인 콘텐츠 디스크립터(3,4)면 is_active=False."""
    result = _parse_game_data(
        99, _steam_data(required_age=0, content_descriptor_ids=[3]), None, None
    )

    assert result["is_active"] is False


def test_parse_game_data_adult_by_genre_inactive():
    """장르에 성인 표지(Sexual Content)가 있으면 is_active=False."""
    result = _parse_game_data(
        99,
        _steam_data(genres=[{"id": "1", "description": "Sexual Content"}]),
        None,
        None,
    )

    assert result["is_active"] is False


def test_parse_game_data_adult_by_title_keyword_inactive():
    """제목에 성인 키워드가 있으면 is_active=False."""
    result = _parse_game_data(99, _steam_data(name="Hentai Puzzle"), None, None)

    assert result["is_active"] is False


def test_parse_game_data_mature_game_stays_active():
    """폭력(디스크립터 2) 등 비성인 성숙 콘텐츠는 활성 유지."""
    result = _parse_game_data(
        99, _steam_data(required_age=0, content_descriptor_ids=[2]), None, None
    )

    assert result["is_active"] is True


def test_parse_game_data_review_score_calculated():
    """리뷰 긍정 비율 정확히 계산 (소수점 2자리)."""
    reviews = _reviews(total=1000, positive=950)
    result = _parse_game_data(730, _steam_data(), reviews, None)

    assert result["review_score"] == 95.0
    assert result["review_count"] == 1000


def test_parse_game_data_no_reviews():
    """리뷰 없음: review_score=None, review_count=0."""
    result = _parse_game_data(730, _steam_data(), None, None)

    assert result["review_score"] is None
    assert result["review_count"] == 0


def test_parse_game_data_with_current_players():
    """현재 접속자 수 저장 + updated_at 설정."""
    result = _parse_game_data(730, _steam_data(), None, 12345)

    assert result["current_players"] == 12345
    assert result["current_players_updated_at"] is not None


def test_parse_game_data_korean_supported():
    """한국어 지원 여부 파싱 — Korean 포함."""
    result = _parse_game_data(730, _steam_data(supported_languages="English, Korean"), None, None)
    assert result["is_korean_supported"] is True


def test_parse_game_data_korean_not_supported():
    """한국어 미지원."""
    result = _parse_game_data(730, _steam_data(supported_languages="English, French"), None, None)
    assert result["is_korean_supported"] is False


def test_parse_game_data_korean_locale():
    """l=korean 응답 (한국어 문자열)도 True 처리."""
    result = _parse_game_data(730, _steam_data(supported_languages="영어, 한국어"), None, None)
    assert result["is_korean_supported"] is True


@pytest.mark.parametrize(
    "date_str,expected",
    [
        ("Jan 1, 2020", date(2020, 1, 1)),
        ("1 Jan, 2020", date(2020, 1, 1)),
        ("January 1, 2020", date(2020, 1, 1)),
        ("2020년 01월 01일", date(2020, 1, 1)),
        ("2020", date(2020, 1, 1)),  # 연도만 있는 경우
    ],
)
def test_parse_release_date_formats(date_str: str, expected: date):
    """다양한 Steam 날짜 형식 파싱."""
    data = _steam_data(release_date_str=date_str)
    result = _parse_game_data(730, data, None, None)
    assert result["release_date"] == expected


def test_parse_coming_soon_no_release_date():
    """coming_soon=True 이면 release_date=None."""
    data = _steam_data()
    data["release_date"] = {"coming_soon": True, "date": "2099"}
    result = _parse_game_data(730, data, None, None)
    assert result["release_date"] is None


def test_parse_trait_vector_length():
    """trait_vector 는 항상 길이 6."""
    result = _parse_game_data(730, _steam_data(), None, None)
    assert len(result["trait_vector"]) == 6


def test_parse_steam_url():
    """steam_url은 앱 ID 기반 URL."""
    result = _parse_game_data(730, _steam_data(), None, None)
    assert result["steam_url"] == "https://store.steampowered.com/app/730/"


# ── fetch_and_save_games ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_and_save_games_success():
    """정상 수집: success 카운트 증가, upsert 호출."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    data = _steam_data()
    reviews = _reviews()
    players = 5000

    with (
        patch("app.game.service.fetch_app_details", return_value=data),
        patch("app.game.service.fetch_app_reviews", return_value=reviews),
        patch("app.game.service.fetch_current_players", return_value=players),
        patch("app.game.service.upsert_game", new_callable=AsyncMock) as mock_upsert,
    ):
        success, failed = await fetch_and_save_games(mock_session, [730, 570], concurrency=2)

    assert success == 2
    assert failed == 0
    assert mock_upsert.call_count == 2


@pytest.mark.asyncio
async def test_fetch_and_save_games_non_game_counted_as_failed():
    """type!=game (fetch_app_details → None): failed 카운트."""
    mock_session = AsyncMock()

    with (
        patch("app.game.service.fetch_app_details", return_value=None),
        patch("app.game.service.fetch_app_reviews", return_value=None),
        patch("app.game.service.fetch_current_players", return_value=None),
    ):
        success, failed = await fetch_and_save_games(mock_session, [999], concurrency=1)

    assert success == 0
    assert failed == 1


@pytest.mark.asyncio
async def test_fetch_and_save_games_db_error_counted_as_failed():
    """DB 저장 실패 시 rollback 후 failed 카운트."""
    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()

    with (
        patch("app.game.service.fetch_app_details", return_value=_steam_data()),
        patch("app.game.service.fetch_app_reviews", return_value=None),
        patch("app.game.service.fetch_current_players", return_value=None),
        patch("app.game.service.upsert_game", side_effect=Exception("DB error")),
    ):
        success, failed = await fetch_and_save_games(mock_session, [730], concurrency=1)

    assert success == 0
    assert failed == 1
    mock_session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_and_save_games_empty_list():
    """빈 app_ids → 즉시 (0, 0) 반환."""
    mock_session = AsyncMock()
    success, failed = await fetch_and_save_games(mock_session, [], concurrency=5)
    assert success == 0
    assert failed == 0
