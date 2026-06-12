from typing import Literal

from fastapi import Response

from app.core.config import settings


def _is_production() -> bool:
    return settings.APP_ENV == "production"


def _get_refresh_cookie_domain() -> str | None:
    if _is_production():
        return ".gembti.cloud"
    return None


def _get_refresh_cookie_samesite() -> Literal["lax", "none"]:
    if _is_production():
        return "none"
    return "lax"


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    secure = _is_production()
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite=_get_refresh_cookie_samesite(),
        domain=_get_refresh_cookie_domain(),
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        path=settings.REFRESH_COOKIE_PATH,
    )


def delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        secure=_is_production(),
        httponly=True,
        samesite=_get_refresh_cookie_samesite(),
        domain=_get_refresh_cookie_domain(),
    )
