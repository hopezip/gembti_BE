from fastapi import Response

from app.core.config import settings


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    is_dev = settings.APP_ENV == "development"

    cookie_domain = None if is_dev else ".gembti.cloud"

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=not is_dev,
        samesite="lax",
        domain=cookie_domain,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        path=settings.REFRESH_COOKIE_PATH,
    )


def delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        secure=settings.APP_ENV != "development",
        httponly=True,
        samesite="lax" if settings.APP_ENV != "development" else "none",
        domain=".gembti.cloud",
    )
