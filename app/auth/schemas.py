from datetime import date, datetime
from enum import StrEnum
import re

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.auth.models import EmailVerificationPurpose, Gender, LoginProvider, UserStatus
from app.auth.password_policy import validate_password_policy


class EmailCodeSendRequest(BaseModel):
    email: EmailStr
    purpose: EmailVerificationPurpose = EmailVerificationPurpose.SIGNUP


class EmailCodeVerifyRequest(EmailCodeSendRequest):
    code: str = Field(pattern=r"^\d{6}$")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=100)
    password_confirm: str
    nickname: str = Field(min_length=2, max_length=8)
    gender: Gender | None = None
    birth_date: date | None = None
    terms_agreed: bool
    privacy_agreed: bool

    @model_validator(mode="after")
    def validate_signup(self) -> "SignupRequest":
        if self.password != self.password_confirm:
            raise ValueError("비밀번호와 비밀번호 확인이 일치하지 않습니다.")

        validate_password_policy(self.password)

        if not re.fullmatch(r"[가-힣A-Za-z0-9]+", self.nickname):
            raise ValueError("닉네임에는 특수문자를 사용할 수 없습니다.")
        if not self.terms_agreed or not self.privacy_agreed:
            raise ValueError("필수 약관에 동의해야 합니다.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserFlowStatus(StrEnum):
    NEEDS_SURVEY = "NEEDS_SURVEY"
    READY = "READY"


class MessageResponse(BaseModel):
    message: str


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


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(AccessTokenResponse):
    pass
