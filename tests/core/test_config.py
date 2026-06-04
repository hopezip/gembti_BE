import pytest

from app.core.config import get_settings, settings


def test_settings_singleton():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_required_fields_exist():
    assert settings.DATABASE_URL
    assert settings.SECRET_KEY
    assert settings.ALGORITHM == "HS256"


def test_token_expiry_positive():
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS > 0
    assert settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS > 0
    assert settings.EMAIL_VERIFIED_TTL_SECONDS > 0


def test_allowed_origins_is_list():
    assert isinstance(settings.ALLOWED_ORIGINS, list)
    assert len(settings.ALLOWED_ORIGINS) > 0
