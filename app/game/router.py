from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.game.schemas import (
    CategoryOption,
    GameDetailResponse,
    GenreOption,
    NewReleasesResponse,
    SearchResponse,
    SortOption,
    TrendingGamesResponse,
)
from app.game.service import (
    get_game_detail_service,
    get_new_releases_service,
    get_trending_games_service,
    search_games_service,
)

router = APIRouter(prefix="/games", tags=["게임"])

_500: dict[int | str, dict[str, Any]] = {500: {"description": "Internal Server Error"}}
_404_500: dict[int | str, dict[str, Any]] = {404: {"description": "Not Found"}, **_500}


@router.get("/search", response_model=SearchResponse, responses=_500)
async def search_games_api(
    q: str = Query(default="", description="검색어 (제목·장르)"),
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    sort: SortOption = Query(default=SortOption.POPULAR, description="정렬 기준"),
    category: list[CategoryOption] = Query(default=[], description="카테고리 필터 — 상위"),
    genre: list[GenreOption] = Query(default=[], description="장르 필터 — 하위"),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    return await search_games_service(
        db,
        q=q,
        page=page,
        sort=sort,
        genres=[str(g) for g in genre],
        categories=[str(c) for c in category],
    )


@router.get("/trending", response_model=TrendingGamesResponse, responses=_500)
async def trending_games_api(
    limit: int = Query(default=10, ge=1, description="반환 개수"),
    db: AsyncSession = Depends(get_db),
) -> TrendingGamesResponse:
    return await get_trending_games_service(db, limit=limit)


@router.get("/new-releases", response_model=NewReleasesResponse, responses=_500)
async def new_releases_api(
    limit: int = Query(default=10, ge=1, description="반환 개수"),
    db: AsyncSession = Depends(get_db),
) -> NewReleasesResponse:
    return await get_new_releases_service(db, limit=limit)


@router.get("/{game_id}", response_model=GameDetailResponse, responses=_404_500)
async def game_detail_api(
    game_id: int,
    db: AsyncSession = Depends(get_db),
) -> GameDetailResponse:
    return await get_game_detail_service(db, game_id)
