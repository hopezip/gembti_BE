from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.auth.schemas import AuthUserResponse, normalize_birth_date_value, normalize_gender_value
from app.core.enums import Gender
from app.steam.models import SteamSyncStatus


class SteamLinkRequest(BaseModel):
    steam_id: str = Field(pattern=r"^\d{17}$")


class SteamLinkResponse(BaseModel):
    steam_linked: bool
    steam_id_64: str
    steam_sync_status: SteamSyncStatus


class SteamCallbackResult(BaseModel):
    result: str
    is_new_user: bool = False
    steam_linked: bool = False
    steam_sync_status: SteamSyncStatus | None = None


class SteamCompleteSignupRequest(BaseModel):
    signup_token: str
    email: EmailStr
    nickname: str = Field(min_length=2, max_length=8, pattern=r"^[가-힣A-Za-z0-9]+$")
    age_confirmed: bool
    gender: Gender | None = None
    birth_date: date | None = None

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, value: object) -> object:
        return normalize_gender_value(value)

    @field_validator("birth_date", mode="before")
    @classmethod
    def normalize_birth_date(cls, value: object) -> object:
        return normalize_birth_date_value(value)

    @model_validator(mode="after")
    def validate_age_confirmation(self) -> "SteamCompleteSignupRequest":
        if not self.age_confirmed:
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
