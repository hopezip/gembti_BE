from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import issue_auth_tokens
from app.core.dependencies import get_current_user_id, get_db
from app.core.exceptions import BadRequestException
from app.steam.schemas import SteamLinkRequest, SteamLinkResponse, SteamStatusResponse
from app.steam.service import (
    build_steam_login_url,
    complete_steam_login,
    get_frontend_steam_callback_url,
    get_steam_status,
    link_steam_account,
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
    await issue_auth_tokens(response, user)
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
