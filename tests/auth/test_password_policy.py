import pytest

from app.auth.password_policy import validate_password_policy


def test_password_policy_reports_number_and_special_character() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_password_policy("onlyletters")

    assert "비밀번호에는 숫자와 특수문자가 포함되어야 합니다." in str(exc_info.value)


def test_password_policy_reports_special_character() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_password_policy("Password123")

    assert "비밀번호에는 특수문자가 포함되어야 합니다." in str(exc_info.value)


def test_password_policy_accepts_valid_password() -> None:
    validate_password_policy("Password!1")
