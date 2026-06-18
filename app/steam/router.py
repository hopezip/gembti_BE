from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.refresh_store import validate_refresh_token
from app.core.config import settings
from app.core.dependencies import get_current_user_id, get_db
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.steam.service import (
    build_steam_login_url,
    complete_steam_connect,
    complete_steam_login,
    get_frontend_steam_callback_url,
    link_steam_for_logged_in_user,
    start_steam_connect,
)

router = APIRouter(tags=["Steam"])

_err = lambda msg: {"content": {"application/json": {"example": {"error": msg}}}}  # noqa: E731


@router.get(
    "/auth/steam",
    status_code=status.HTTP_302_FOUND,
    responses={
        500: _err("스팀 연동 서버 오류"),
    },
)
async def steam_auth_login_api() -> RedirectResponse:
    return RedirectResponse(build_steam_login_url(), status_code=status.HTTP_302_FOUND)


@router.get("/auth/steam/callback", status_code=status.HTTP_302_FOUND)
async def steam_auth_callback_api(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    response = RedirectResponse(
        get_frontend_steam_callback_url(result="success"),
        status_code=status.HTTP_302_FOUND,
    )
    params = dict(request.query_params)

    refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    current_user_id = await validate_refresh_token(refresh_token) if refresh_token else None

    try:
        if current_user_id is not None:
            link_response = await link_steam_for_logged_in_user(
                db=db,
                user_id=current_user_id,
                params=params,
            )
            response.headers["location"] = get_frontend_steam_callback_url(
                result="success",
                is_new_user=False,
                steam_linked=True,
                steam_id=link_response.steam_id_64,
            )
            return response

        user, is_new_user, steam_id_64 = await complete_steam_login(
            db=db,
            response=response,
            params=params,
        )
    except (BadRequestException, ConflictException, NotFoundException):
        response.headers["location"] = get_frontend_steam_callback_url(
            result="failed",
            reason="steam_auth_failed",
        )
        return response

    response.headers["location"] = get_frontend_steam_callback_url(
        result="success",
        is_new_user=is_new_user,
        steam_linked=True,
        steam_id=str(steam_id_64),
    )
    return response


@router.get(
    "/steam/connect",
    status_code=status.HTTP_302_FOUND,
    responses={
        401: _err("인증 실패"),
        500: _err("스팀 연동 서버 오류"),
    },
)
async def steam_connect_api(
    user_id: int = Depends(get_current_user_id),
) -> RedirectResponse:
    return RedirectResponse(
        await start_steam_connect(user_id),
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/steam/connect/callback", status_code=status.HTTP_302_FOUND)
async def steam_connect_callback_api(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    response = RedirectResponse(
        get_frontend_steam_callback_url(result="success"),
        status_code=status.HTTP_302_FOUND,
    )
    try:
        await complete_steam_connect(
            db=db,
            state=request.query_params.get("state"),
            params=dict(request.query_params),
        )
    except (BadRequestException, ConflictException, NotFoundException):
        response.headers["location"] = get_frontend_steam_callback_url(
            result="failed",
            reason="steam_connect_failed",
        )
        return response

    response.headers["location"] = get_frontend_steam_callback_url(
        result="success",
        is_new_user=False,
        steam_linked=True,
    )
    return response
