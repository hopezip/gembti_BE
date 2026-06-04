from fastapi import Response

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.auth.refresh_store import delete_refresh_token, save_refresh_token
from app.auth.schemas import AccessTokenResponse
from app.auth.token_blacklist import blacklist_access_token
from app.core.security import create_access_token, create_refresh_token


async def issue_auth_tokens(
    response: Response,
    user_id: int,
    provider: str,
) -> AccessTokenResponse:
    access_token = create_access_token(subject=user_id, provider=provider)
    refresh_token = create_refresh_token(subject=user_id, provider=provider)
    await save_refresh_token(user_id, refresh_token, provider)
    set_refresh_cookie(response, refresh_token)

    return AccessTokenResponse(access_token=access_token)


async def logout_tokens(
    response: Response,
    access_token: str,
    refresh_token: str,
    user_id: int,
) -> None:
    await blacklist_access_token(access_token)
    await delete_refresh_token(refresh_token, user_id=user_id)
    delete_refresh_cookie(response)
