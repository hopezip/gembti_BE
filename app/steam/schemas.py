from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.auth.models import Gender
from app.auth.schemas import AuthUserResponse
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


class SteamCompleteSignupRequest(BaseModel):
    signup_token: str
    email: EmailStr
    nickname: str = Field(min_length=2, max_length=8, pattern=r"^[가-힣A-Za-z0-9]+$")
    age_agreed: bool
    gender: Gender | None = None
    birth_date: date | None = None

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @model_validator(mode="after")
    def validate_age_agreement(self) -> "SteamCompleteSignupRequest":
        if not self.age_agreed:
            raise ValueError("만 15세 이상만 가입할 수 있습니다.")
        return self


class SteamCompleteSignupResponse(BaseModel):
    status: str = "success"
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


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
