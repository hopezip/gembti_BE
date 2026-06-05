from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from app.auth.models import LoginProvider, User, UserStatus
from app.auth.repository import get_user_by_id, get_user_by_nickname
from app.auth.service import issue_auth_tokens
from app.core.config import settings
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.steam.client import (
    build_steam_openid_url,
    get_player_summary,
    verify_steam_openid,
)
from app.steam.models import SteamAccount, SteamSyncStatus
from app.steam.repository import (
    get_steam_account_by_steam_id,
    get_steam_account_by_user_id,
    save_steam_account,
)
from app.steam.schemas import SteamLinkResponse, SteamStatusResponse

if TYPE_CHECKING:
    from fastapi import Response
    from sqlalchemy.ext.asyncio import AsyncSession

STEAM_CLAIMED_ID_PATTERN = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")


def get_steam_return_to() -> str:
    return f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/v1/auth/steam/callback"


def get_steam_realm() -> str:
    return settings.BACKEND_BASE_URL.rstrip("/")


def get_frontend_steam_callback_url(**query: str | int | bool | None) -> str:
    callback_url = (
        f"{settings.FRONTEND_BASE_URL.rstrip('/')}/" f"{settings.STEAM_CALLBACK_PATH.strip('/')}"
    )
    filtered_query = {key: str(value).lower() for key, value in query.items() if value is not None}
    if not filtered_query:
        return callback_url
    return f"{callback_url}?{urlencode(filtered_query)}"


def build_steam_login_url() -> str:
    return build_steam_openid_url(
        return_to=get_steam_return_to(),
        realm=get_steam_realm(),
    )


def extract_steam_id_64(params: dict[str, str]) -> int:
    claimed_id = params.get("openid.claimed_id")
    if claimed_id is None:
        raise BadRequestException("Steam 인증 응답에 SteamID가 없습니다.")

    match = STEAM_CLAIMED_ID_PATTERN.fullmatch(claimed_id)
    if match is None:
        raise BadRequestException("Steam 인증 응답이 올바르지 않습니다.")

    return int(match.group(1))


async def verify_and_extract_steam_id(params: dict[str, str]) -> int:
    if not await verify_steam_openid(params):
        raise BadRequestException("Steam 인증에 실패했습니다.")
    return extract_steam_id_64(params)


async def get_or_create_steam_user(
    db: AsyncSession,
    steam_id_64: int,
    avatar_url: str | None = None,
) -> tuple[User, bool]:
    steam_account = await get_steam_account_by_steam_id(db, steam_id_64)
    if steam_account is not None:
        user = steam_account.user
        steam_account.avatar_url = avatar_url or steam_account.avatar_url
        await db.commit()
        await db.refresh(user)
        return user, False

    user = User(
        email=f"steam_{steam_id_64}@steam.local",
        password_hash=None,
        nickname=await create_unique_steam_nickname(db, steam_id_64),
        login_provider=LoginProvider.STEAM,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()

    await save_steam_account(
        db,
        SteamAccount(
            user_id=user.id,
            steam_id_64=steam_id_64,
            avatar_url=avatar_url,
            steam_sync_status=SteamSyncStatus.FAILED,
        ),
    )
    await db.commit()
    await db.refresh(user)
    return user, True


async def create_unique_steam_nickname(db: AsyncSession, steam_id_64: int) -> str:
    base_nickname = f"steam{str(steam_id_64)[-8:]}"
    nickname = base_nickname

    suffix = 1
    while await get_user_by_nickname(db, nickname):
        nickname = f"{base_nickname}{suffix}"
        suffix += 1

    return nickname


async def complete_steam_login(
    db: AsyncSession,
    response: Response,
    params: dict[str, str],
) -> tuple[User, bool]:
    steam_id_64 = await verify_and_extract_steam_id(params)
    profile = await get_player_summary(steam_id_64)
    avatar_url = None if profile is None else profile.get("avatarfull")

    user, is_new_user = await get_or_create_steam_user(
        db=db,
        steam_id_64=steam_id_64,
        avatar_url=avatar_url,
    )
    await issue_auth_tokens(response, user)
    return user, is_new_user


async def link_steam_account(
    db: AsyncSession,
    user_id: int,
    steam_id: str,
) -> SteamLinkResponse:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundException("사용자를 찾을 수 없습니다.")

    if await get_steam_account_by_user_id(db, user_id):
        raise ConflictException("이미 Steam 계정이 연동되어 있습니다.")

    steam_id_64 = int(steam_id)
    if await get_steam_account_by_steam_id(db, steam_id_64):
        raise ConflictException("이미 다른 사용자에게 연동된 Steam 계정입니다.")

    profile = await get_player_summary(steam_id_64)
    steam_account = await save_steam_account(
        db,
        SteamAccount(
            user_id=user_id,
            steam_id_64=steam_id_64,
            avatar_url=None if profile is None else profile.get("avatarfull"),
            steam_sync_status=SteamSyncStatus.FAILED,
        ),
    )
    await db.commit()

    return SteamLinkResponse(
        steam_linked=True,
        steam_id_64=str(steam_account.steam_id_64),
        steam_sync_status=steam_account.steam_sync_status,
    )


async def get_steam_status(db: AsyncSession, user_id: int) -> SteamStatusResponse:
    steam_account = await get_steam_account_by_user_id(db, user_id)
    if steam_account is None:
        return SteamStatusResponse(steam_linked=False)

    return SteamStatusResponse(
        steam_linked=True,
        steam_id_64=str(steam_account.steam_id_64),
        steam_avatar_url=steam_account.avatar_url,
        steam_sync_status=steam_account.steam_sync_status,
        last_synced_at=steam_account.last_synced_at,
    )
