from dataclasses import dataclass
from enum import StrEnum
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
STEAM_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
STEAM_OPENID_NS = "http://specs.openid.net/auth/2.0"
STEAM_PLAYER_SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
STEAM_OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
STEAM_RECENTLY_PLAYED_URL = (
    "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v0001/"
)
STEAM_API_TIMEOUT_SECONDS = 30.0
STEAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class SteamLibraryVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    EMPTY = "empty"
    FAILED = "failed"


@dataclass(frozen=True)
class SteamOwnedGamesResult:
    visibility: SteamLibraryVisibility
    games: list[dict[str, Any]]
    game_count: int | None = None


class SteamLibraryPayloadError(RuntimeError):
    """Steam의 보유 게임 응답 구조나 게임 수가 계약과 다를 때 발생한다."""


@dataclass(frozen=True)
class SteamRecentlyPlayedResult:
    visibility: SteamLibraryVisibility
    games: list[dict[str, Any]]


def parse_owned_games_payload(payload: dict[str, Any]) -> SteamOwnedGamesResult:
    response_body = payload.get("response")
    if not isinstance(response_body, dict):
        logger.error("Steam 보유 게임 응답에 response 객체가 없습니다.")
        raise SteamLibraryPayloadError("Steam API response 객체 누락")

    if not response_body:
        return SteamOwnedGamesResult(SteamLibraryVisibility.PRIVATE, [])

    game_count = response_body.get("game_count")
    if isinstance(game_count, bool) or not isinstance(game_count, int) or game_count < 0:
        logger.error("Steam 보유 게임 응답의 game_count가 올바르지 않습니다.")
        raise SteamLibraryPayloadError("Steam API game_count 형식 오류")

    raw_games = response_body.get("games")
    if raw_games is None and game_count == 0:
        return SteamOwnedGamesResult(SteamLibraryVisibility.EMPTY, [], game_count=0)
    if not isinstance(raw_games, list):
        logger.error("Steam 보유 게임 응답의 games가 목록이 아닙니다.")
        raise SteamLibraryPayloadError("Steam API games 형식 오류")

    games: list[dict[str, Any]] = []
    app_ids: list[int] = []
    for game in raw_games:
        if not isinstance(game, dict):
            raise SteamLibraryPayloadError("Steam API 게임 항목 형식 오류")
        app_id = game.get("appid")
        if isinstance(app_id, bool) or not isinstance(app_id, int) or app_id <= 0:
            raise SteamLibraryPayloadError("Steam API AppID 형식 오류")
        games.append(game)
        app_ids.append(app_id)

    received_count = len(games)
    if game_count != received_count:
        logger.error(
            "Steam 보유 게임 수 불일치: reported=%d received=%d",
            game_count,
            received_count,
        )
        raise SteamLibraryPayloadError(
            f"Steam API 게임 수 불일치: reported={game_count}, received={received_count}"
        )
    if len(set(app_ids)) != received_count:
        logger.error("Steam 보유 게임 응답에 중복 AppID가 있습니다.")
        raise SteamLibraryPayloadError("Steam API 중복 AppID")

    if not games:
        return SteamOwnedGamesResult(SteamLibraryVisibility.EMPTY, [], game_count=0)

    return SteamOwnedGamesResult(SteamLibraryVisibility.PUBLIC, games, game_count=game_count)


def build_steam_openid_url(return_to: str, realm: str) -> str:
    query = urlencode(
        {
            "openid.ns": STEAM_OPENID_NS,
            "openid.mode": "checkid_setup",
            "openid.return_to": return_to,
            "openid.realm": realm,
            "openid.identity": STEAM_IDENTIFIER_SELECT,
            "openid.claimed_id": STEAM_IDENTIFIER_SELECT,
        }
    )
    return f"{STEAM_OPENID_URL}?{query}"


async def verify_steam_openid(params: dict[str, str]) -> bool:
    payload = {key: value for key, value in params.items() if key.startswith("openid.")}
    payload["openid.mode"] = "check_authentication"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                STEAM_OPENID_URL,
                data=payload,
                headers=STEAM_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return False

    return "is_valid:true" in response.text


async def get_player_summary(steam_id_64: int) -> dict[str, Any] | None:
    if not settings.STEAM_API_KEY:
        return None

    params: dict[str, str | int] = {
        "key": settings.STEAM_API_KEY,
        "steamids": str(steam_id_64),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                STEAM_PLAYER_SUMMARIES_URL,
                params=params,
                headers=STEAM_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None

    try:
        players = response.json().get("response", {}).get("players", [])
    except ValueError:
        return None

    if not players:
        return None
    return players[0]


async def get_owned_games(steam_id_64: int) -> SteamOwnedGamesResult:
    if not settings.STEAM_API_KEY:
        return SteamOwnedGamesResult(SteamLibraryVisibility.FAILED, [])

    params: dict[str, str | int] = {
        "key": settings.STEAM_API_KEY,
        "steamid": str(steam_id_64),
        "include_appinfo": 0,
        "include_played_free_games": 1,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=STEAM_API_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(
                STEAM_OWNED_GAMES_URL,
                params=params,
                headers=STEAM_HEADERS,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return SteamOwnedGamesResult(SteamLibraryVisibility.FAILED, [])

    return parse_owned_games_payload(payload)


async def get_recently_played_games(steam_id_64: int) -> SteamRecentlyPlayedResult:
    if not settings.STEAM_API_KEY:
        return SteamRecentlyPlayedResult(SteamLibraryVisibility.FAILED, [])

    params = {
        "key": settings.STEAM_API_KEY,
        "steamid": str(steam_id_64),
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=STEAM_API_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(
                STEAM_RECENTLY_PLAYED_URL,
                params=params,
                headers=STEAM_HEADERS,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return SteamRecentlyPlayedResult(SteamLibraryVisibility.FAILED, [])

    response_body = payload.get("response")
    if not isinstance(response_body, dict) or "games" not in response_body:
        return SteamRecentlyPlayedResult(SteamLibraryVisibility.PRIVATE, [])

    games = response_body.get("games") or []
    if not games:
        return SteamRecentlyPlayedResult(SteamLibraryVisibility.EMPTY, [])

    return SteamRecentlyPlayedResult(SteamLibraryVisibility.PUBLIC, games)
