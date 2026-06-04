from fastapi import Response

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.core.config import settings


def test_set_refresh_cookie() -> None:
    response = Response()

    set_refresh_cookie(response, "refresh-token")

    cookie = response.headers["set-cookie"]
    assert f"{settings.REFRESH_COOKIE_NAME}=refresh-token" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/auth" in cookie


def test_delete_refresh_cookie() -> None:
    response = Response()

    delete_refresh_cookie(response)

    cookie = response.headers["set-cookie"]
    assert f"{settings.REFRESH_COOKIE_NAME}=" in cookie
    assert "Max-Age=0" in cookie
