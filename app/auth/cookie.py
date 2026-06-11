from fastapi import Response

from app.core.config import settings


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    is_dev = settings.APP_ENV == "development"

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=not is_dev,
        samesite="lax" if not is_dev else None,
        domain=None,
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
