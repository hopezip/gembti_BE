from datetime import date, datetime
from enum import StrEnum
import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.auth.models import EmailVerificationPurpose, Gender, LoginProvider, UserStatus
from app.auth.password_policy import validate_password_policy


class EmailCodeSendRequest(BaseModel):
    email: EmailStr
    purpose: EmailVerificationPurpose = EmailVerificationPurpose.SIGNUP

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_purpose(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().upper().replace("-", "_")
        purpose_map = {
            "SIGNUP": EmailVerificationPurpose.SIGNUP,
            "PASSWORD_RESET": EmailVerificationPurpose.PASSWORD_RESET,
            "PASSWORDRESET": EmailVerificationPurpose.PASSWORD_RESET,
            "RESET_PASSWORD": EmailVerificationPurpose.PASSWORD_RESET,
            "PASSWORD/RESET": EmailVerificationPurpose.PASSWORD_RESET,
        }
        return purpose_map.get(normalized, normalized)


class EmailCodeVerifyRequest(EmailCodeSendRequest):
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return re.sub(r"\D", "", value)


def normalize_gender_value(value: object) -> object:
    if not isinstance(value, str):
        return value

    normalized = value.strip().lower()
    gender_map = {
        "남성": Gender.MALE,
        "male": Gender.MALE,
        "m": Gender.MALE,
        "여성": Gender.FEMALE,
        "female": Gender.FEMALE,
        "f": Gender.FEMALE,
        "기타": Gender.OTHER,
        "other": Gender.OTHER,
    }
    return gender_map.get(normalized, normalized)


def normalize_birth_date_value(value: object) -> object:
    if not isinstance(value, str):
        return value

    normalized = value.strip()
    if not normalized:
        return None

    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.rstrip(".")

    for separator in (".", "/"):
        if separator in normalized:
            parts = normalized.split(separator)
            if len(parts) == 3:
                year, month, day = parts
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    return normalized


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=100)
    password_confirm: str
    nickname: str = Field(min_length=2, max_length=8)
    gender: Gender | None = None
    birth_date: date | None = None
    age_confirmed: bool

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, value: object) -> object:
        return normalize_gender_value(value)

    @field_validator("birth_date", mode="before")
    @classmethod
    def normalize_birth_date(cls, value: object) -> object:
        return normalize_birth_date_value(value)

    @model_validator(mode="after")
    def validate_signup(self) -> "SignupRequest":
        if self.password != self.password_confirm:
            raise ValueError("비밀번호와 비밀번호 확인이 일치하지 않습니다.")

        validate_password_policy(self.password)

        if not re.fullmatch(r"[가-힣A-Za-z0-9]+", self.nickname):
            raise ValueError("닉네임에는 특수문자를 사용할 수 없습니다.")
        if not self.age_confirmed:
            raise ValueError("만 15세 이상만 가입할 수 있습니다.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=100)
    password_confirm: str

    @model_validator(mode="after")
    def validate_password_reset(self) -> "PasswordResetRequest":
        if self.password != self.password_confirm:
            raise ValueError("비밀번호와 비밀번호 확인이 일치하지 않습니다.")

        validate_password_policy(self.password)
        return self


class NicknameCheckResponse(BaseModel):
    available: bool
    message: str


class UserFlowStatus(StrEnum):
    NEEDS_SURVEY = "NEEDS_SURVEY"
    READY = "READY"


class MessageResponse(BaseModel):
    message: str


class WithdrawRequest(BaseModel):
    password: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=100)
    detail: str | None = Field(default=None, max_length=1000)


class WithdrawResponse(BaseModel):
    message: str
    hard_delete_after: datetime


class UserResponse(BaseModel):
    id: int
    email: str
    nickname: str
    bio: str | None
    login_provider: LoginProvider
    status: UserStatus
    steam_linked: bool
    steam_id_64: str | None
    steam_avatar_url: str | None
    steam_sync_status: str | None
    last_synced_at: datetime | None
    has_completed_survey: bool = False
    user_flow_status: UserFlowStatus = UserFlowStatus.NEEDS_SURVEY

    model_config = {"from_attributes": True}


class AuthUserResponse(BaseModel):
    id: int
    email: str
    nickname: str
    bio: str | None
    login_provider: LoginProvider
    status: UserStatus
    steam_linked: bool
    steam_id_64: str | None
    steam_avatar_url: str | None
    steam_sync_status: str | None
    last_synced_at: datetime | None

    model_config = {"from_attributes": True}


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(AccessTokenResponse):
    user: AuthUserResponse
