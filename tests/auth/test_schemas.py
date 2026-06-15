from pydantic import ValidationError
import pytest

from app.auth.models import EmailVerificationPurpose
from app.auth.schemas import (
    EmailCodeSendRequest,
    EmailCodeVerifyRequest,
    PasswordResetRequest,
    SignupRequest,
)
from app.core.enums import Gender
from app.steam.schemas import SteamCompleteSignupRequest


def valid_signup_data() -> dict[str, object]:
    return {
        "email": "test@example.com",
        "password": "Password!1",
        "password_confirm": "Password!1",
        "nickname": "테스터1",
        "age_confirmed": True,
    }


def test_signup_schema_accepts_valid_request() -> None:
    request = SignupRequest.model_validate(valid_signup_data())
    assert request.email == "test@example.com"


def test_email_code_schema_accepts_lowercase_purpose() -> None:
    request = EmailCodeSendRequest.model_validate(
        {
            "email": "test@example.com",
            "purpose": "password_reset",
        }
    )

    assert request.purpose == EmailVerificationPurpose.PASSWORD_RESET


def test_email_verify_schema_normalizes_code_separators() -> None:
    request = EmailCodeVerifyRequest.model_validate(
        {
            "email": "test@example.com",
            "purpose": "signup",
            "code": "1 2 3-4 5 6",
        }
    )

    assert request.purpose == EmailVerificationPurpose.SIGNUP
    assert request.code == "123456"


def test_signup_schema_accepts_frontend_display_values() -> None:
    request = SignupRequest.model_validate(
        {
            **valid_signup_data(),
            "gender": "남성",
            "birth_date": "2000. 01. 15.",
        }
    )

    assert request.gender == Gender.MALE
    assert request.birth_date is not None
    assert request.birth_date.isoformat() == "2000-01-15"


def test_steam_complete_signup_schema_accepts_frontend_display_values() -> None:
    request = SteamCompleteSignupRequest.model_validate(
        {
            "signup_token": "steam_signup_token",
            "email": "steam@example.com",
            "nickname": "스팀유저",
            "age_confirmed": True,
            "gender": "여성",
            "birth_date": "2000. 1. 5.",
        }
    )

    assert request.gender == Gender.FEMALE
    assert request.birth_date is not None
    assert request.birth_date.isoformat() == "2000-01-05"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password", "onlyletters"),
        ("password_confirm", "different!1"),
        ("nickname", "bad!name"),
        ("age_confirmed", False),
    ],
)
def test_signup_schema_rejects_invalid_request(field: str, value: object) -> None:
    data = valid_signup_data()
    data[field] = value

    with pytest.raises(ValidationError):
        SignupRequest.model_validate(data)


def test_signup_schema_reports_all_missing_password_parts() -> None:
    data = valid_signup_data()
    data["password"] = "onlyletters"
    data["password_confirm"] = "onlyletters"

    with pytest.raises(ValidationError) as exc_info:
        SignupRequest.model_validate(data)

    assert "비밀번호에는 숫자와 특수문자가 포함되어야 합니다." in str(exc_info.value)


def test_password_reset_schema_accepts_valid_request() -> None:
    request = PasswordResetRequest.model_validate(
        {
            "email": "test@example.com",
            "password": "NewPassword!1",
            "password_confirm": "NewPassword!1",
        }
    )

    assert request.email == "test@example.com"


def test_password_reset_schema_rejects_mismatched_password() -> None:
    with pytest.raises(ValidationError):
        PasswordResetRequest.model_validate(
            {
                "email": "test@example.com",
                "password": "NewPassword!1",
                "password_confirm": "OtherPassword!1",
            }
        )
