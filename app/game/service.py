from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from html.parser import HTMLParser
import logging
import re
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.recommendation.vectorizer import game_to_vector
from app.core.recommendation.schemas import _rating_from_score
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
    discount_percent = 0
    if data.get("is_free"):
        price_krw = 0
    else:
        price_ov = data.get("price_overview", {})
        raw = price_ov.get("final")
        price_krw = raw // 100 if raw is not None else None  # Steam은 모든 통화를 100배로 반환
        discount_percent = int(price_ov.get("discount_percent") or 0)

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
        "discount_percent": discount_percent,
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


# ── 게임 API 서비스 ──────────────────────────────────────────────────────────

# Steam 장르 → 정규화 한글 (영문/한글 양방향)
_GENRE_NORMALIZE: dict[str, str] = {
    # English
    "Action": "액션",
    "Adventure": "어드벤처",
    "RPG": "롤플레잉",
    "Strategy": "전략",
    "Simulation": "시뮬레이션",
    "Casual": "캐주얼",
    "Massively Multiplayer": "대규모 멀티플레이어",
    "Sports": "스포츠",
    "Racing": "레이싱",
    "Indie": "인디",
    # Korean (Steam l=korean)
    "액션": "액션",
    "어드벤처": "어드벤처",
    "롤플레잉 게임": "롤플레잉",
    "롤플레잉": "롤플레잉",
    "전략": "전략",
    "시뮬레이션": "시뮬레이션",
    "캐주얼": "캐주얼",
    "대규모 멀티플레이어": "대규모 멀티플레이어",
    "스포츠": "스포츠",
    "레이싱": "레이싱",
    "인디": "인디",
}

# Steam 카테고리 → 정규화 한글 (영문/한글 양방향)
_CATEGORY_NORMALIZE: dict[str, str] = {
    # English
    "Single-player": "싱글플레이어",
    "Co-op": "협동",
    "Online Co-op": "온라인 협동",
    "Multi-player": "멀티플레이어",
    "PvP": "플레이어 대전",
    "Online PvP": "온라인 플레이어 대전",
    # Korean (Steam l=korean)
    "싱글 플레이어": "싱글플레이어",
    "싱글플레이어": "싱글플레이어",
    "협동": "협동",
    "온라인 협동": "온라인 협동",
    "멀티플레이어": "멀티플레이어",
    "플레이어 대전": "플레이어 대전",
    "온라인 플레이어 대전": "온라인 플레이어 대전",
    "온라인 PvP": "온라인 플레이어 대전",
}

# Steam 카테고리 설명 → FE 플레이 모드 코드 (정규화 이름 기준으로도 처리)
_CATEGORY_TO_PLAY_MODE: dict[str, str] = {
    "Single-player": "SINGLE",
    "싱글 플레이어": "SINGLE",
    "싱글플레이어": "SINGLE",
    "Co-op": "CO_OP",
    "Online Co-op": "CO_OP",
    "협동": "CO_OP",
    "온라인 협동": "CO_OP",
    "Multi-player": "MULTI",
    "멀티플레이어": "MULTI",
    "Online PvP": "MULTI",
    "온라인 PvP": "MULTI",
    "온라인 플레이어 대전": "MULTI",
    "PvP": "MULTI",
    "플레이어 대전": "MULTI",
}


def _parse_requirements_html(html: str) -> dict:
    """Steam PC requirements HTML에서 사양 항목 추출."""
    result = {"os": "", "processor": "", "memory": "", "graphics": "", "storage": ""}
    if not html:
        return result

    # <br>, <li> → 줄바꿈으로 치환 후 나머지 태그 제거
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    field_map = {
        "os": ["OS"],
        "processor": ["Processor", "CPU"],
        "memory": ["Memory"],
        "graphics": ["Graphics", "GPU", "Video Card"],
        "storage": ["Storage", "Hard Drive", "Hard Disk Space"],
    }
    for key, labels in field_map.items():
        for label in labels:
            m = re.search(rf"{re.escape(label)}:\s*(.+)", text, re.IGNORECASE)
            if m:
                result[key] = m.group(1).strip().rstrip(",;")
                break

    return result


def _parse_supported_languages(lang_str: str) -> tuple[list[str], list[str]]:
    """Steam 언어 문자열에서 오디오 지원 언어와 인터페이스 언어 분리.

    '*' 표기 언어는 풀 오디오 지원.
    """
    raw = lang_str.split("<br>")[0]
    raw = re.sub(r"<[^>]+>", "", raw)

    audio: list[str] = []
    interface: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "*" in token:
            name = token.replace("*", "").strip()
            audio.append(name)
            interface.append(name)
        else:
            interface.append(token)
    return audio, interface


def _normalize_genres(genres: list[str]) -> list[str]:
    """Steam 장르 목록을 정규화 한글 이름으로 변환. 미인식 장르는 그대로 유지."""
    seen: set[str] = set()
    result: list[str] = []
    for g in genres:
        normalized = _GENRE_NORMALIZE.get(g, g)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _normalize_categories(categories: list[str]) -> list[str]:
    """Steam 카테고리 목록을 정규화 한글 이름으로 변환. 미인식 카테고리는 제외."""
    seen: set[str] = set()
    result: list[str] = []
    for c in categories:
        normalized = _CATEGORY_NORMALIZE.get(c)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _genre_db_values(normalized: str) -> list[str]:
    """정규화 장르 이름 → DB에 저장된 가능한 모든 값 목록."""
    return [k for k, v in _GENRE_NORMALIZE.items() if v == normalized] or [normalized]


def _category_db_values(normalized: str) -> list[str]:
    """정규화 카테고리 이름 → DB에 저장된 가능한 모든 값 목록."""
    return [k for k, v in _CATEGORY_NORMALIZE.items() if v == normalized] or [normalized]


def _derive_play_modes(categories: list[str]) -> list[str]:
    seen: set[str] = set()
    modes: list[str] = []
    for cat in categories:
        mode = _CATEGORY_TO_PLAY_MODE.get(cat)
        if mode and mode not in seen:
            seen.add(mode)
            modes.append(mode)
    return modes


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


def _strip_html(html: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


def _build_price_info(price_krw: int | None, discount_percent: int, is_free: bool) -> dict:
    original = 0 if is_free else (price_krw or 0)
    if discount_percent > 0 and original > 0:
        sale = int(original * (1 - discount_percent / 100))
        return {"original_price": original, "sale_price": sale, "discount_rate": discount_percent}
    return {"original_price": original, "sale_price": None, "discount_rate": 0}


def _game_to_summary(game: Game) -> dict:  # type: ignore[name-defined]  # noqa: F821
    return {
        "game_id": game.id,
        "title": game.title,
        "thumbnail_url": game.image_url,
        "genres": game.genres,
        "rating": _rating_from_score(game.review_score),
    }


async def search_games_service(
    session: AsyncSession,
    q: str,
    page: int,
    sort: str,
    genres: list[str] | None = None,
    categories: list[str] | None = None,
) -> SearchResponse:  # type: ignore[name-defined]  # noqa: F821
    from app.game.repository import search_games as repo_search
    from app.game.schemas import (
        GameSearchItemResponse,
        PriceInfoResponse,
        SearchDataResponse,
        SearchResponse,
    )

    # 정규화 이름 → DB 저장 가능한 값 목록으로 변환
    filter_genres = [_genre_db_values(g) for g in (genres or [])]
    filter_categories = [_category_db_values(c) for c in (categories or [])]

    games, total = await repo_search(
        session,
        q=q,
        page=page,
        sort=sort,
        filter_genres=filter_genres,
        filter_categories=filter_categories,
    )
    page_size = 12
    items = []
    for g in games:
        price = _build_price_info(g.price_krw, g.discount_percent, g.is_free)
        items.append(
            GameSearchItemResponse(
                game_id=g.id,
                title=g.title,
                thumbnail_url=g.image_url,
                categories=_normalize_categories(g.category),
                genres=_normalize_genres(g.genres),
                rating=_rating_from_score(g.review_score),
                price_info=PriceInfoResponse(**price),
            )
        )

    return SearchResponse(
        data=SearchDataResponse(
            games=items,
            total_count=total,
            has_more=(page * page_size) < total,
        )
    )


async def get_trending_games_service(
    session: AsyncSession,
    limit: int = 12,
) -> TrendingGamesResponse:  # type: ignore[name-defined]  # noqa: F821
    from app.game.repository import get_trending_games
    from app.game.schemas import HomeGameItem, TrendingGamesResponse

    games = await get_trending_games(session, limit=limit)
    return TrendingGamesResponse(
        data=[
            HomeGameItem(
                game_id=g.id,
                title=g.title,
                thumbnail_url=g.image_url,
                genres=_normalize_genres(g.genres),
                rating=_rating_from_score(g.review_score),
            )
            for g in games
        ]
    )


async def get_new_releases_service(
    session: AsyncSession,
    limit: int = 12,
) -> NewReleasesResponse:  # type: ignore[name-defined]  # noqa: F821
    from app.game.repository import get_new_releases
    from app.game.schemas import HomeGameItem, NewReleasesResponse

    games = await get_new_releases(session, limit=limit)
    return NewReleasesResponse(
        data=[
            HomeGameItem(
                game_id=g.id,
                title=g.title,
                thumbnail_url=g.image_url,
                genres=_normalize_genres(g.genres),
                rating=_rating_from_score(g.review_score),
                is_new=True,
            )
            for g in games
        ]
    )


async def get_game_detail_service(
    session: AsyncSession,
    game_id: int,
) -> GameDetailResponse:  # type: ignore[name-defined]  # noqa: F821
    from app.game.repository import get_developer_games, get_game_by_id
    from app.game.schemas import (
        GameDetailDataResponse,
        GameDetailResponse,
        GameSummaryResponse,
        PriceInfoResponse,
        SystemRequirementsResponse,
        SystemSpecResponse,
    )

    game = await get_game_by_id(session, game_id)
    if game is None:
        raise NotFoundException("게임을 찾을 수 없습니다.")

    detail_json = game.steam_detail_json or {}

    # 개발사/퍼블리셔
    devs = detail_json.get("developers") or []
    pubs = detail_json.get("publishers") or []
    developer = devs[0] if devs else ""
    publisher = pubs[0] if pubs else ""

    # 유사 게임 / 개발사 게임 병렬 조회
    dev_games = await get_developer_games(session, developer, game.id)

    price = _build_price_info(game.price_krw, game.discount_percent, game.is_free)

    # PC 사양
    pc_req = detail_json.get("pc_requirements") or {}
    min_spec = _parse_requirements_html(
        pc_req.get("minimum", "") if isinstance(pc_req, dict) else ""
    )
    rec_spec = _parse_requirements_html(
        pc_req.get("recommended", "") if isinstance(pc_req, dict) else ""
    )

    # 스크린샷
    screenshots = [s["path_full"] for s in detail_json.get("screenshots", []) if "path_full" in s]

    # 트레일러
    trailer_url: str | None = None
    movies = detail_json.get("movies") or []
    if movies:
        m = movies[0]
        trailer_url = (
            m.get("webm", {}).get("max")
            or m.get("webm", {}).get("480")
            or m.get("mp4", {}).get("max")
            or m.get("mp4", {}).get("480")
        )

    # 언어
    audio_langs, iface_langs = _parse_supported_languages(
        detail_json.get("supported_languages", "")
    )

    # 배경 이미지
    background = detail_json.get("background") or detail_json.get("background_raw") or ""

    # 연령 등급
    required_age = int(detail_json.get("required_age") or 0)
    age_rating = f"{required_age}세 이용가" if required_age > 0 else "전체 이용가"

    on_sale = price["sale_price"] is not None

    return GameDetailResponse(
        data=GameDetailDataResponse(
            game_id=game.id,
            title=game.title,
            description=game.description or "",
            full_description=_strip_html(
                detail_json.get("detailed_description")
                or detail_json.get("about_the_game")
                or game.description
                or ""
            ),
            genres=_normalize_genres(game.genres),
            categories=_normalize_categories(game.category),
            rating=_rating_from_score(game.review_score),
            review_count=game.review_count,
            price_info=PriceInfoResponse(**price),
            developer=developer,
            publisher=publisher,
            release_date=game.release_date.isoformat() if game.release_date else None,
            thumbnail_url=game.image_url,
            theme_image_url=background,
            banner_url=background,
            screenshot_urls=screenshots,
            trailer_url=trailer_url,
            system_requirements=SystemRequirementsResponse(
                minimum=SystemSpecResponse(**min_spec),
                recommended=SystemSpecResponse(**rec_spec),
            ),
            audio_languages=audio_langs,
            interface_languages=iface_langs,
            play_modes=_derive_play_modes(game.category),
            korean_sub=game.is_korean_supported,
            age_rating=age_rating,
            on_sale=on_sale,
            developer_games=[GameSummaryResponse(**_game_to_summary(g)) for g in dev_games],
        )
    )
