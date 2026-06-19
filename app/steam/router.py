from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.refresh_store import validate_refresh_token
from app.core.config import settings
from app.core.dependencies import get_current_user_id, get_db
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.steam.schemas import SteamSyncResponse
from app.steam.service import (
    build_steam_login_url,
    complete_steam_login,
    get_frontend_steam_callback_url,
    link_steam_for_logged_in_user,
    sync_steam_library,
    unlink_steam_account,
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
    except ConflictException:
        response.headers["location"] = get_frontend_steam_callback_url(
            result="failed",
            reason="steam_already_linked",
        )
        return response
    except (BadRequestException, NotFoundException):
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


@router.delete(
    "/steam/unlink",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: _err("인증 실패"),
        404: _err("연동된 Steam 계정 없음"),
    },
)
async def steam_unlink_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await unlink_steam_account(db, user_id)


@router.post(
    "/steam/sync",
    response_model=SteamSyncResponse,
    responses={
        401: _err("인증 실패"),
        404: _err("연동된 Steam 계정 없음"),
    },
)
async def steam_sync_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SteamSyncResponse:
    return await sync_steam_library(db, user_id)
