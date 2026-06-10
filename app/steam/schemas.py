from datetime import datetime

from pydantic import BaseModel, Field

from app.steam.models import SteamSyncStatus


class SteamLinkRequest(BaseModel):
    steam_id: str = Field(pattern=r"^\d{17}$")


class SteamLinkResponse(BaseModel):
    steam_linked: bool
    steam_id_64: str
    steam_sync_status: SteamSyncStatus


class SteamStatusResponse(BaseModel):
    steam_linked: bool
    steam_id_64: str | None = None
    steam_avatar_url: str | None = None
    steam_sync_status: SteamSyncStatus | None = None
    last_synced_at: datetime | None = None
    library_games_count: int = 0
    next: str | None = None
    message: str | None = None


class SteamCallbackResult(BaseModel):
    result: str
    is_new_user: bool = False
    steam_linked: bool = False
    steam_sync_status: SteamSyncStatus | None = None


class SteamSyncResponse(BaseModel):
    steam_sync_status: SteamSyncStatus
    synced_count: int
    last_synced_at: datetime | None = None
    next: str
    message: str


class SteamRecentlyPlayedGameResponse(BaseModel):
    steam_app_id: int
    playtime_minutes: int
    playtime_2weeks: int = 0


class SteamRecentlyPlayedResponse(BaseModel):
    steam_sync_status: SteamSyncStatus
    games: list[SteamRecentlyPlayedGameResponse]
    message: str | None = None
