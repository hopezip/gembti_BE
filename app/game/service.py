from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.recommendation.vectorizer import game_to_vector
from app.game.client import fetch_app_details, fetch_app_reviews, fetch_current_players
from app.game.repository import upsert_game

logger = logging.getLogger(__name__)

# Steam 장르/카테고리 ID → 영문 이름 (trait_mapper 키와 일치해야 함)
# l=korean 등 현지화 언어로 받아도 벡터화는 영문 기준으로 수행한다.
_GENRE_ID_EN: dict[str, str] = {
    "1": "Action",
    "25": "Adventure",
    "3": "RPG",
    "2": "Strategy",
    "28": "Simulation",
    "4": "Casual",
    "29": "Massively Multiplayer",
    "18": "Sports",
    "9": "Racing",
    "23": "Indie",
}
_CATEGORY_ID_EN: dict[str, str] = {
    "9": "Co-op",
    "38": "Online Co-op",
    "1": "Multi-player",
    "49": "PvP",
    "36": "Online PvP",
    "2": "Single-player",
}

_DATE_FORMATS = [
    "%b %d, %Y",  # Jan 1, 2020
    "%d %b, %Y",  # 1 Jan, 2020
    "%B %d, %Y",  # January 1, 2020
    "%d %B, %Y",  # 1 January, 2020
    "%Y년 %m월 %d일",  # 2020년 1월 1일 (l=korean)
    "%Y",  # 2020
]


def _is_korean_supported(supported_languages: str) -> bool:
    """l=korean 응답(한국어)과 l=english 응답(Korean) 모두 대응."""
    return "Korean" in supported_languages or "한국어" in supported_languages


def _parse_release_date(date_str: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_game_data(
    app_id: int,
    data: dict,
    reviews: dict | None,
    current_players: int | None,
) -> dict:
    """Steam appdetails 응답을 Game 모델 필드로 변환한다."""
    genres_raw = data.get("genres", [])
    categories_raw = data.get("categories", [])

    # DB 저장: 현지화된 이름 그대로 (l=korean 시 한글)
    genres = [g["description"] for g in genres_raw]
    categories = [c["description"] for c in categories_raw]

    # 벡터화: ID → 영문 이름 변환 (trait_mapper 키와 일치)
    genres_for_vector = [
        _GENRE_ID_EN.get(str(g.get("id", "")), g["description"]) for g in genres_raw
    ]
    categories_for_vector = [
        _CATEGORY_ID_EN.get(str(c.get("id", "")), c["description"]) for c in categories_raw
    ]

    price_krw: int | None
    if data.get("is_free"):
        price_krw = 0
    else:
        price_ov = data.get("price_overview", {})
        raw = price_ov.get("final")
        price_krw = raw // 100 if raw is not None else None  # Steam은 모든 통화를 100배로 반환

    release_date = None
    rd = data.get("release_date", {})
    if not rd.get("coming_soon") and rd.get("date"):
        release_date = _parse_release_date(rd["date"])

    required_age = int(data.get("required_age") or 0)
    is_active = required_age < 18

    # 리뷰 통계: 긍정 비율(0~100) + 전체 수
    review_score = None
    review_count = 0
    if reviews:
        total = reviews.get("total_reviews", 0)
        positive = reviews.get("total_positive", 0)
        if total > 0:
            review_score = round(positive / total * 100, 2)
        review_count = total

    # 현재 접속자 수
    current_players_updated_at = None
    if current_players is not None:
        current_players_updated_at = datetime.now(UTC)

    return {
        "app_id": app_id,
        "title": data.get("name", ""),
        "image_url": data.get("header_image"),
        "description": data.get("short_description"),
        "genres": genres,
        "category": categories,
        "trait_vector": game_to_vector(genres_for_vector, categories_for_vector),
        "release_date": release_date,
        "price_krw": price_krw,
        "is_free": data.get("is_free", False),
        "is_korean_supported": _is_korean_supported(data.get("supported_languages", "")),
        "is_active": is_active,
        "steam_url": f"https://store.steampowered.com/app/{app_id}/",
        "review_score": review_score,
        "review_count": review_count,
        "current_players": current_players,
        "current_players_updated_at": current_players_updated_at,
        "steam_detail_json": data,
    }


async def fetch_and_save_games(
    session: AsyncSession,
    app_ids: list[int],
    concurrency: int = 5,
) -> tuple[int, int]:
    """Steam API에서 게임 목록을 비동기로 수집해 DB에 저장한다.

    게임별로 appdetails / appreviews / current_players 3개 API를 동시 호출한다.
    HTTP 요청은 concurrency 수만큼 동시 실행하고,
    DB 저장은 세션 안전성을 위해 순차 처리한다.

    Returns:
        (성공 수, 실패 수)
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _fetch_one(
        app_id: int,
        client: httpx.AsyncClient,
    ) -> tuple[int, dict | None, dict | None, int | None]:
        async with semaphore:
            details, reviews, players = await asyncio.gather(
                fetch_app_details(app_id, client),
                fetch_app_reviews(app_id, client),
                fetch_current_players(app_id, client),
            )
        return app_id, details, reviews, players

    async with httpx.AsyncClient(timeout=15.0) as client:
        fetch_results = await asyncio.gather(
            *[_fetch_one(app_id, client) for app_id in app_ids],
            return_exceptions=True,
        )

    success, failed = 0, 0

    for result in fetch_results:
        if isinstance(result, Exception):
            logger.warning("게임 수집 중 예외 발생: %s", result)
            failed += 1
            continue

        assert isinstance(result, tuple)
        app_id, data, reviews, players = result
        if data is None:
            failed += 1
            continue

        try:
            game_data = _parse_game_data(app_id, data, reviews, players)
            await upsert_game(session, game_data)
            await session.commit()
            success += 1
        except Exception as e:
            logger.error("게임 저장 실패 app_id=%s: %s", app_id, e)
            await session.rollback()
            failed += 1

    return success, failed
