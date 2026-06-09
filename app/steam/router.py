from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_id, get_db
from app.core.exceptions import BadRequestException
from app.steam.schemas import (
    SteamLinkRequest,
    SteamLinkResponse,
    SteamRecentlyPlayedResponse,
    SteamStatusResponse,
    SteamSyncResponse,
)
from app.steam.service import (
    build_steam_login_url,
    complete_steam_login,
    get_frontend_steam_callback_url,
    get_recently_played,
    get_steam_status,
    link_steam_account,
    sync_steam_library,
)

router = APIRouter(tags=["Steam"])


@router.get("/auth/steam", status_code=status.HTTP_302_FOUND)
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
    try:
        user, is_new_user = await complete_steam_login(
            db=db,
            response=response,
            params=dict(request.query_params),
        )
    except BadRequestException:
        response.headers["location"] = get_frontend_steam_callback_url(
            result="failed",
            reason="steam_auth_failed",
        )
        return response

    response.headers["location"] = get_frontend_steam_callback_url(
        result="success",
        is_new_user=is_new_user,
        steam_linked=True,
        user_id=user.id,
    )
    return response


@router.post("/steam/link", response_model=SteamLinkResponse)
async def steam_link_api(
    request: SteamLinkRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SteamLinkResponse:
    response = await link_steam_account(db, user_id, request.steam_id)
    await db.commit()
    return response


@router.get("/steam/status", response_model=SteamStatusResponse)
async def steam_status_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SteamStatusResponse:
    return await get_steam_status(db, user_id)


@router.post("/steam/sync", response_model=SteamSyncResponse)
async def steam_sync_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SteamSyncResponse:
    response = await sync_steam_library(db, user_id)
    await db.commit()
    return response


@router.get("/steam/recently-played", response_model=SteamRecentlyPlayedResponse)
async def steam_recently_played_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SteamRecentlyPlayedResponse:
    return await get_recently_played(db, user_id)
