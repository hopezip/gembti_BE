from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_id, get_db
from app.core.exceptions import BadRequestException
from app.steam.schemas import (
    SteamLinkRequest,
    SteamLinkResponse,
)
from app.steam.service import (
    build_steam_login_url,
    complete_steam_login,
    get_frontend_steam_callback_url,
    link_steam_account,
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
    try:
        user, is_new_user, signup_token = await complete_steam_login(
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

    if user is None:
        response.headers["location"] = get_frontend_steam_callback_url(
            result="signup_required",
            is_new_user=is_new_user,
            signup_token=signup_token,
        )
    else:
        response.headers["location"] = get_frontend_steam_callback_url(
            result="success",
            is_new_user=is_new_user,
            steam_linked=True,
        )
    return response


@router.post(
    "/steam/link",
    response_model=SteamLinkResponse,
    responses={
        400: _err("Steam ID 형식이 올바르지 않습니다."),
        401: _err("인증 실패"),
        404: _err("사용자를 찾을 수 없습니다."),
        409: _err("이미 다른 사용자에게 연동된 Steam 계정입니다."),
    },
)
async def steam_link_api(
    request: SteamLinkRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SteamLinkResponse:
    response = await link_steam_account(db, user_id, request.steam_id)
    await db.commit()
    return response
