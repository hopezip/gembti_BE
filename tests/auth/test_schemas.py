from pydantic import ValidationError
import pytest

from app.auth.schemas import PasswordResetRequest, SignupRequest


def valid_signup_data() -> dict[str, object]:
    return {
        "email": "test@example.com",
        "password": "Password!1",
        "password_confirm": "Password!1",
        "nickname": "테스터1",
        "age_confirmed": True,
        "terms_agreed": True,
        "privacy_agreed": True,
    }


def test_signup_schema_accepts_valid_request() -> None:
    request = SignupRequest.model_validate(valid_signup_data())
    assert request.email == "test@example.com"


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
