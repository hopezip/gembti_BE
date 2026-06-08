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


class SteamCallbackResult(BaseModel):
    result: str
    is_new_user: bool = False
    steam_linked: bool = False
    steam_sync_status: SteamSyncStatus | None = None
