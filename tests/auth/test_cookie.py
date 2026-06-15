from fastapi import Response
import pytest

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.core.config import settings


def test_set_refresh_cookie_for_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    response = Response()

    set_refresh_cookie(response, "refresh-token")

    cookie = response.headers["set-cookie"]
    assert f"{settings.REFRESH_COOKIE_NAME}=refresh-token" in cookie
    assert "HttpOnly" in cookie
    assert f"Path={settings.REFRESH_COOKIE_PATH}" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie
    assert "Domain=.gembti.cloud" not in cookie


def test_set_refresh_cookie_for_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    response = Response()

    set_refresh_cookie(response, "refresh-token")

    cookie = response.headers["set-cookie"]
    assert f"{settings.REFRESH_COOKIE_NAME}=refresh-token" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=none" in cookie
    assert "Domain=.gembti.cloud" in cookie


def test_delete_refresh_cookie_for_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    response = Response()

    delete_refresh_cookie(response)

    cookie = response.headers["set-cookie"]
    assert f"{settings.REFRESH_COOKIE_NAME}=" in cookie
    assert "Max-Age=0" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie
    assert "Domain=.gembti.cloud" not in cookie


def test_delete_refresh_cookie_for_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    response = Response()

    delete_refresh_cookie(response)

    cookie = response.headers["set-cookie"]
    assert f"{settings.REFRESH_COOKIE_NAME}=" in cookie
    assert "Max-Age=0" in cookie
    assert "Secure" in cookie
    assert "SameSite=none" in cookie
    assert "Domain=.gembti.cloud" in cookie
