from __future__ import annotations

import httpx

STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
STEAM_APP_REVIEWS_URL = "https://store.steampowered.com/appreviews"
STEAM_CURRENT_PLAYERS_URL = (
    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)


async def fetch_app_details(app_id: int, client: httpx.AsyncClient) -> dict | None:
    """Steam Store API에서 단일 앱 상세 정보를 가져온다.

    type != 'game' 이거나 요청 실패 시 None을 반환한다.
    """
    try:
        res = await client.get(
            STEAM_APP_DETAILS_URL,
            params={"appids": app_id, "cc": "kr", "l": "korean"},
            timeout=10.0,
        )
        res.raise_for_status()
    except httpx.HTTPError:
        return None

    payload = res.json().get(str(app_id), {})
    if not payload.get("success"):
        return None

    data = payload.get("data", {})
    if data.get("type") != "game":
        return None

    return data


async def fetch_app_list() -> list[int]:
    """IStoreService/GetAppList/v1/ 로 전체 게임 app_id 목록을 가져온다.

    - API 키 필요 (STEAM_API_KEY)
    - last_appid 기반 페이지네이션으로 전체 목록 수집
    - include_games=1, include_dlc=0 으로 게임만 필터링
    """
    from app.core.config import settings

    app_ids: list[int] = []
    last_appid: int | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params: dict = {
                "key": settings.STEAM_API_KEY,
                "include_games": 1,
                "include_dlc": 0,
                "include_software": 0,
                "include_videos": 0,
                "include_hardware": 0,
                "max_results": 50000,
            }
            if last_appid is not None:
                params["last_appid"] = last_appid

            try:
                res = await client.get(STEAM_APP_LIST_URL, params=params)
                res.raise_for_status()
            except httpx.HTTPError:
                break

            body = res.json().get("response", {})
            apps = body.get("apps", [])
            app_ids.extend(app["appid"] for app in apps)

            if not body.get("have_more_results"):
                break
            last_appid = body.get("last_appid")

    return app_ids


async def fetch_app_reviews(app_id: int, client: httpx.AsyncClient) -> dict | None:
    """Steam Store 리뷰 통계를 가져온다.

    Returns:
        query_summary dict: total_positive, total_negative, total_reviews 포함.
        실패 시 None 반환.
    """
    try:
        res = await client.get(
            f"{STEAM_APP_REVIEWS_URL}/{app_id}",
            params={
                "json": 1,
                "language": "all",
                "review_type": "all",
                "purchase_type": "all",
                "num_per_page": 0,
            },
            timeout=10.0,
        )
        res.raise_for_status()
        return res.json().get("query_summary")
    except httpx.HTTPError:
        return None


async def fetch_current_players(app_id: int, client: httpx.AsyncClient) -> int | None:
    """Steam API에서 현재 접속자 수를 가져온다."""
    try:
        res = await client.get(
            STEAM_CURRENT_PLAYERS_URL,
            params={"appid": app_id},
            timeout=5.0,
        )
        res.raise_for_status()
        return res.json().get("response", {}).get("player_count")
    except httpx.HTTPError:
        return None
