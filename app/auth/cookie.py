from fastapi import Response

from app.core.config import settings


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    secure = settings.APP_ENV != "development"
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        path="/auth",
    )


def delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path="/auth",
        secure=settings.APP_ENV != "development",
        httponly=True,
        samesite="none" if settings.APP_ENV != "development" else "lax",
    )
