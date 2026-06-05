from fastapi import Response

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.auth.schemas import AccessTokenResponse
from app.auth.token_blacklist import blacklist_access_token
from app.core.security import create_access_token, create_refresh_token


def issue_auth_tokens(
    response: Response,
    user_id: int,
    provider: str,
) -> tuple[AccessTokenResponse, str]:
    access_token = create_access_token(subject=user_id, provider=provider)
    refresh_token = create_refresh_token(subject=user_id, provider=provider)
    set_refresh_cookie(response, refresh_token)

    return AccessTokenResponse(access_token=access_token), refresh_token


async def logout_access_token(response: Response, access_token: str) -> None:
    await blacklist_access_token(access_token)
    delete_refresh_cookie(response)
