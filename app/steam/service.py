from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from app.auth.models import LoginProvider, User, UserStatus
from app.auth.repository import get_user_by_id, get_user_by_nickname
from app.auth.service import issue_auth_tokens
from app.core.config import settings
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.steam.client import (
    SteamLibraryVisibility,
    build_steam_openid_url,
    get_owned_games,
    get_player_summary,
    get_recently_played_games,
    verify_steam_openid,
)
from app.steam.models import SteamAccount, SteamSyncStatus, UserLibraryGame
from app.steam.repository import (
    get_library_games_by_user_id,
    get_steam_account_by_steam_id,
    get_steam_account_by_user_id,
    save_steam_account,
    upsert_library_games,
)
from app.steam.schemas import (
    SteamLinkResponse,
    SteamRecentlyPlayedGameResponse,
    SteamRecentlyPlayedResponse,
    SteamStatusResponse,
    SteamSyncResponse,
)

if TYPE_CHECKING:
    from fastapi import Response
    from sqlalchemy.ext.asyncio import AsyncSession

STEAM_CLAIMED_ID_PATTERN = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")
STEAM_NEXT_RECOMMENDATION = "RECOMMENDATION"
STEAM_NEXT_SURVEY = "SURVEY"
STEAM_NEXT_RETRY = "RETRY"


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
        await db.flush()
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
    await db.flush()
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
    await db.commit()
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

    return SteamLinkResponse(
        steam_linked=True,
        steam_id_64=str(steam_account.steam_id_64),
        steam_sync_status=steam_account.steam_sync_status,
    )


async def get_steam_status(db: AsyncSession, user_id: int) -> SteamStatusResponse:
    steam_account = await get_steam_account_by_user_id(db, user_id)
    if steam_account is None:
        return SteamStatusResponse(
            steam_linked=False,
            next=STEAM_NEXT_SURVEY,
            message="Steam 계정이 연동되어 있지 않습니다.",
        )

    library_games = await get_library_games_by_user_id(db, user_id)
    library_games_count = len(library_games)

    return SteamStatusResponse(
        steam_linked=True,
        steam_id_64=str(steam_account.steam_id_64),
        steam_avatar_url=steam_account.avatar_url,
        steam_sync_status=steam_account.steam_sync_status,
        last_synced_at=steam_account.last_synced_at,
        library_games_count=library_games_count,
        next=get_next_step_for_sync_status(steam_account.steam_sync_status),
        message=get_message_for_sync_status(steam_account.steam_sync_status),
    )


async def sync_steam_library(db: AsyncSession, user_id: int) -> SteamSyncResponse:
    steam_account = await get_steam_account_by_user_id(db, user_id)
    if steam_account is None:
        raise NotFoundException("Steam 계정이 연동되어 있지 않습니다.")

    owned_games = await get_owned_games(steam_account.steam_id_64)
    synced_at = datetime.now(UTC)

    if owned_games.visibility == SteamLibraryVisibility.PUBLIC:
        library_games = [
            build_user_library_game(user_id=user_id, steam_game=steam_game, synced_at=synced_at)
            for steam_game in owned_games.games
        ]
        synced_count = await upsert_library_games(db, user_id, library_games)
        steam_account.steam_sync_status = SteamSyncStatus.SUCCESS
        steam_account.last_synced_at = synced_at
        await db.flush()
        return SteamSyncResponse(
            steam_sync_status=SteamSyncStatus.SUCCESS,
            synced_count=synced_count,
            last_synced_at=synced_at,
            next=STEAM_NEXT_RECOMMENDATION,
            message="Steam 라이브러리 동기화가 완료되었습니다.",
        )

    steam_account.steam_sync_status = map_visibility_to_sync_status(owned_games.visibility)
    steam_account.last_synced_at = synced_at
    await db.flush()
    return SteamSyncResponse(
        steam_sync_status=steam_account.steam_sync_status,
        synced_count=0,
        last_synced_at=synced_at,
        next=get_next_step_for_sync_status(steam_account.steam_sync_status),
        message=get_message_for_sync_status(steam_account.steam_sync_status),
    )


async def get_recently_played(db: AsyncSession, user_id: int) -> SteamRecentlyPlayedResponse:
    steam_account = await get_steam_account_by_user_id(db, user_id)
    if steam_account is None:
        raise NotFoundException("Steam 계정이 연동되어 있지 않습니다.")

    recent_games = await get_recently_played_games(steam_account.steam_id_64)
    sync_status = map_visibility_to_sync_status(recent_games.visibility)
    games = [
        SteamRecentlyPlayedGameResponse(
            steam_app_id=parse_steam_int(steam_game["appid"]),
            playtime_minutes=parse_steam_int(steam_game.get("playtime_forever", 0)),
            playtime_2weeks=parse_steam_int(steam_game.get("playtime_2weeks", 0)),
        )
        for steam_game in recent_games.games
        if "appid" in steam_game
    ]
    return SteamRecentlyPlayedResponse(
        steam_sync_status=sync_status,
        games=games,
        message=None if games else get_message_for_sync_status(sync_status),
    )


def build_user_library_game(
    user_id: int,
    steam_game: dict[str, object],
    synced_at: datetime,
) -> UserLibraryGame:
    return UserLibraryGame(
        user_id=user_id,
        steam_app_id=parse_steam_int(steam_game["appid"]),
        playtime_minutes=parse_steam_int(steam_game.get("playtime_forever", 0)),
        last_played_at=parse_steam_timestamp(steam_game.get("rtime_last_played")),
        synced_at=synced_at,
    )


def parse_steam_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(parse_steam_int(value), tz=UTC)


def parse_steam_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0


def map_visibility_to_sync_status(visibility: SteamLibraryVisibility) -> SteamSyncStatus:
    if visibility == SteamLibraryVisibility.PUBLIC:
        return SteamSyncStatus.SUCCESS
    if visibility == SteamLibraryVisibility.PRIVATE:
        return SteamSyncStatus.PRIVATE
    if visibility == SteamLibraryVisibility.EMPTY:
        return SteamSyncStatus.EMPTY
    return SteamSyncStatus.FAILED


def get_next_step_for_sync_status(sync_status: SteamSyncStatus) -> str:
    if sync_status == SteamSyncStatus.SUCCESS:
        return STEAM_NEXT_RECOMMENDATION
    if sync_status in {SteamSyncStatus.PRIVATE, SteamSyncStatus.EMPTY}:
        return STEAM_NEXT_SURVEY
    return STEAM_NEXT_RETRY


def get_message_for_sync_status(sync_status: SteamSyncStatus) -> str:
    if sync_status == SteamSyncStatus.SUCCESS:
        return "Steam 라이브러리 동기화가 완료되었습니다."
    if sync_status == SteamSyncStatus.PRIVATE:
        return "Steam 라이브러리가 비공개입니다. 설문 기반 추천으로 진행합니다."
    if sync_status == SteamSyncStatus.EMPTY:
        return "동기화할 Steam 라이브러리 게임이 없습니다. 설문 기반 추천으로 진행합니다."
    return "Steam 라이브러리 동기화에 실패했습니다. 잠시 후 다시 시도해 주세요."
