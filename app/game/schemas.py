from __future__ import annotations

from pydantic import BaseModel


class PriceInfoResponse(BaseModel):
    original_price: int
    sale_price: int | None
    discount_rate: int


# ── 검색 ─────────────────────────────────────────────────────────────────────

class GameSearchItemResponse(BaseModel):
    game_id: int
    title: str
    thumbnail_url: str | None
    categories: list[str]  # 상위 필터: 싱글플레이어·협동·멀티플레이어 등
    genres: list[str]      # 하위 필터: 액션·RPG·전략 등
    rating: float | None
    price_info: PriceInfoResponse


class SearchDataResponse(BaseModel):
    games: list[GameSearchItemResponse]
    total_count: int
    has_more: bool


class SearchResponse(BaseModel):
    status: str = "SUCCESS"
    data: SearchDataResponse


# ── 필터 옵션 ─────────────────────────────────────────────────────────────────

class PriceRangeOption(BaseModel):
    label: str
    min: int
    max: int


class PlayModeOption(BaseModel):
    value: str
    label: str


class FilterOptionsData(BaseModel):
    categories: list[str]  # 상위 필터: 싱글플레이어·협동·멀티플레이어 등
    genres: list[str]      # 하위 필터: 액션·RPG·전략 등
    price_ranges: list[PriceRangeOption]
    play_modes: list[PlayModeOption]


class FilterOptionsResponse(BaseModel):
    status: str = "SUCCESS"
    data: FilterOptionsData


# ── 홈 공통 카드 ──────────────────────────────────────────────────────────────

class HomeGameItem(BaseModel):
    game_id: int
    title: str
    thumbnail_url: str | None
    genres: list[str]
    rating: float | None
    is_new: bool = False


class TrendingGamesResponse(BaseModel):
    status: str = "SUCCESS"
    data: list[HomeGameItem]


class NewReleasesResponse(BaseModel):
    status: str = "SUCCESS"
    data: list[HomeGameItem]


# ── 게임 상세 ──────────────────────────────────────────────────────────────────

class SystemSpecResponse(BaseModel):
    os: str = ""
    processor: str = ""
    memory: str = ""
    graphics: str = ""
    storage: str = ""


class SystemRequirementsResponse(BaseModel):
    minimum: SystemSpecResponse
    recommended: SystemSpecResponse


class GameSummaryResponse(BaseModel):
    game_id: int
    title: str
    thumbnail_url: str | None
    genres: list[str]
    rating: float | None


class GameDetailDataResponse(BaseModel):
    game_id: int
    title: str
    description: str
    full_description: str
    genres: list[str]
    categories: list[str]
    rating: float | None
    review_count: int
    price_info: PriceInfoResponse
    developer: str
    publisher: str
    release_date: str | None
    thumbnail_url: str | None
    theme_image_url: str
    banner_url: str
    screenshot_urls: list[str]
    trailer_url: str | None
    system_requirements: SystemRequirementsResponse
    audio_languages: list[str]
    interface_languages: list[str]
    play_modes: list[str]
    korean_sub: bool
    age_rating: str
    on_sale: bool
    developer_games: list[GameSummaryResponse]
    ai_match: None = None
    review_stats: None = None


class GameDetailResponse(BaseModel):
    status: str = "SUCCESS"
    data: GameDetailDataResponse
