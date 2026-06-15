from typing import Literal

from fastapi import Response

from app.core.config import settings

SameSitePolicy = Literal["lax", "strict", "none"]


def _is_production() -> bool:
    return settings.APP_ENV == "production"


def _cookie_secure() -> bool:
    return _is_production()


def _cookie_samesite() -> SameSitePolicy:
    return "none" if _is_production() else "lax"


def _cookie_domain() -> str | None:
    return ".gembti.cloud" if _is_production() else None


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        domain=_cookie_domain(),
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        path=settings.REFRESH_COOKIE_PATH,
    )


def delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        secure=_cookie_secure(),
        httponly=True,
        samesite=_cookie_samesite(),
        domain=_cookie_domain(),
    )
