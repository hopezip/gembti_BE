from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

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


@dataclass(frozen=True)
class SteamRecentlyPlayedResult:
    visibility: SteamLibraryVisibility
    games: list[dict[str, Any]]


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
    payload = dict(params)
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

    response_body = payload.get("response")
    if not isinstance(response_body, dict) or "games" not in response_body:
        return SteamOwnedGamesResult(SteamLibraryVisibility.PRIVATE, [])

    games = response_body.get("games") or []
    if not games:
        return SteamOwnedGamesResult(SteamLibraryVisibility.EMPTY, [])

    return SteamOwnedGamesResult(SteamLibraryVisibility.PUBLIC, games)


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
