from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
STEAM_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
STEAM_OPENID_NS = "http://specs.openid.net/auth/2.0"
STEAM_PLAYER_SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"


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
            response = await client.post(STEAM_OPENID_URL, data=payload)
            response.raise_for_status()
        except httpx.HTTPError:
            return False

    return "is_valid:true" in response.text


async def get_player_summary(steam_id_64: int) -> dict[str, Any] | None:
    if not settings.STEAM_API_KEY:
        return None

    params = {
        "key": settings.STEAM_API_KEY,
        "steamids": str(steam_id_64),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(STEAM_PLAYER_SUMMARIES_URL, params=params)
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
