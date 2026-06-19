from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, cast

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.auth.email_sender import send_verification_email
from app.auth.email_verification_store import (
    consume_verified_email,
    delete_verification_code,
    save_verification_code,
    verify_email_code,
)
from app.auth.models import EmailVerificationPurpose, User
from app.auth.refresh_store import (
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    save_refresh_token,
    validate_refresh_token,
)
from app.auth.repository import (
    delete_user_by_id,
    get_user_by_email,
    get_user_by_id,
    get_user_by_nickname,
    get_user_steam_library_rows,
    has_user_stats,
    save_user,
)
from app.auth.schemas import (
    AccessTokenResponse,
    AuthResponse,
    AuthUserResponse,
    LoginRequest,
    MessageResponse,
    NicknameCheckResponse,
    PasswordResetRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    SignupRequest,
    SteamLibraryGameResponse,
    SteamLibraryResponse,
    UserActivityResponse,
    UserFlowStatus,
    UserResponse,
    WithdrawRequest,
    WithdrawResponse,
)
from app.auth.token_blacklist import blacklist_access_token
from app.core.enums import LoginProvider, UserStatus
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

if TYPE_CHECKING:
    from datetime import date

    from fastapi import Response
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.game.models import Game
    from app.steam.models import UserLibraryGame


async def issue_auth_tokens(
    response: Response,
    user: User,
) -> AuthResponse:
    provider = user.login_provider.value
    access_token = create_access_token(subject=user.id, provider=provider)
    refresh_token = create_refresh_token(subject=user.id, provider=provider)
    await save_refresh_token(user.id, refresh_token, provider)
    set_refresh_cookie(response, refresh_token)

    return AuthResponse(access_token=access_token, user=AuthUserResponse.model_validate(user))


async def send_email_code(
    db: AsyncSession,
    email: str,
    purpose: EmailVerificationPurpose,
) -> None:
    normalized_email = email.strip().lower()
    user = await get_user_by_email(db, normalized_email)

    if purpose == EmailVerificationPurpose.SIGNUP and user is not None:
        raise ConflictException("이미 가입된 이메일입니다.")
    if purpose == EmailVerificationPurpose.PASSWORD_RESET and user is None:
        raise BadRequestException("가입되지 않은 이메일입니다.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    await save_verification_code(normalized_email, purpose, code)

    try:
        await send_verification_email(normalized_email, code)
    except Exception:
        await delete_verification_code(normalized_email, purpose)
        raise BadRequestException("이메일 발송에 실패했습니다.") from None


async def verify_email(
    email: str,
    purpose: EmailVerificationPurpose,
    code: str,
) -> None:
    if not await verify_email_code(email, purpose, code):
        raise BadRequestException("인증번호가 만료되었거나 일치하지 않습니다.")


async def signup(
    db: AsyncSession,
    response: Response,
    request: SignupRequest,
) -> AuthResponse:
    email = request.email.lower()

    if await get_user_by_email(db, email):
        raise ConflictException("이미 사용 중인 이메일입니다.")
    if await get_user_by_nickname(db, request.nickname):
        raise ConflictException("이미 사용 중인 닉네임입니다.")
    if not await consume_verified_email(email, EmailVerificationPurpose.SIGNUP):
        raise ForbiddenException("이메일 인증이 필요합니다.")

    user = User(
        email=email,
        password_hash=hash_password(request.password),
        nickname=request.nickname,
        gender=request.gender,
        birth_date=request.birth_date,
        login_provider=LoginProvider.EMAIL,
        status=UserStatus.ACTIVE,
    )
    return await issue_auth_tokens(response, await save_user(db, user))


async def login(
    db: AsyncSession,
    response: Response,
    request: LoginRequest,
) -> AccessTokenResponse:
    user = await get_user_by_email(db, request.email.lower())

    if (
        user is None
        or user.password_hash is None
        or not verify_password(request.password, user.password_hash)
    ):
        raise UnauthorizedException("이메일 또는 비밀번호가 일치하지 않습니다.")
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenException("사용할 수 없는 계정입니다.")

    auth_response = await issue_auth_tokens(response, user)
    return AccessTokenResponse(access_token=auth_response.access_token)


async def check_nickname_available(
    db: AsyncSession,
    nickname: str,
) -> NicknameCheckResponse:
    if not 2 <= len(nickname) <= 8 or not re.fullmatch(r"[가-힣A-Za-z0-9]+", nickname):
        raise BadRequestException("닉네임 형식이 올바르지 않습니다.")

    if await get_user_by_nickname(db, nickname):
        raise ConflictException("이미 사용 중인 닉네임입니다.")

    return NicknameCheckResponse(
        available=True,
        message="사용 가능한 닉네임입니다.",
    )


async def get_me(
    db: AsyncSession,
    user_id: int,
) -> UserResponse:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundException("사용자를 찾을 수 없습니다.")

    steam_library = await build_steam_library_response(db, user.id)
    has_completed_survey = await has_user_stats(db, user.id)

    return UserResponse(
        id=user.id,
        user_id=user.id,
        email=user.email,
        nickname=user.nickname,
        bio=user.bio,
        gender=user.gender,
        birth_date=cast("date | None", user.birth_date),
        login_provider=user.login_provider,
        status=user.status,
        steam_linked=user.steam_linked,
        steam_id_64=user.steam_id_64,
        steam_avatar_url=user.steam_avatar_url,
        steam_sync_status=user.steam_sync_status,
        last_synced_at=user.last_synced_at,
        has_completed_survey=has_completed_survey,
        user_flow_status=(
            UserFlowStatus.READY if has_completed_survey else UserFlowStatus.NEEDS_SURVEY
        ),
        steam_library=steam_library,
    )


async def update_me(
    db: AsyncSession,
    user_id: int,
    request: ProfileUpdateRequest,
) -> ProfileUpdateResponse:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundException("사용자를 찾을 수 없습니다.")

    if "nickname" in request.model_fields_set and request.nickname is not None:
        existing_user = await get_user_by_nickname(db, request.nickname)
        if existing_user is not None and existing_user.id != user.id:
            raise ConflictException("이미 사용 중인 닉네임입니다.")
        user.nickname = request.nickname

    if "bio" in request.model_fields_set:
        user.bio = request.bio
    if "gender" in request.model_fields_set:
        user.gender = request.gender
    if "birth_date" in request.model_fields_set:
        user.birth_date = request.birth_date  # type: ignore[assignment]

    await db.commit()
    return ProfileUpdateResponse(
        profile=ProfileResponse(
            user_id=user.id,
            email=user.email,
            nickname=user.nickname,
            bio=user.bio,
            gender=user.gender,
            birth_date=cast("date | None", user.birth_date),
        )
    )


async def get_my_activity(
    db: AsyncSession,
    user_id: int,
) -> UserActivityResponse:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundException("사용자를 찾을 수 없습니다.")

    steam_library = await build_steam_library_response(db, user.id)
    return UserActivityResponse(
        user_id=user.id,
        steam_linked=user.steam_linked,
        steam_sync_status=user.steam_sync_status,
        library_game_count=steam_library.library_game_count,
        total_playtime_minutes=steam_library.total_playtime_minutes,
        total_playtime_hours=steam_library.total_playtime_hours,
        recent_games=steam_library.games,
    )


async def build_steam_library_response(
    db: AsyncSession,
    user_id: int,
) -> SteamLibraryResponse:
    library_rows = await get_user_steam_library_rows(db, user_id)
    library_games = [
        build_library_game_response(library_game, game) for library_game, game in library_rows
    ]
    total_playtime_minutes = sum(game.playtime_minutes for game in library_games)

    return SteamLibraryResponse(
        library_game_count=len(library_games),
        total_playtime_minutes=total_playtime_minutes,
        total_playtime_hours=minutes_to_hours(total_playtime_minutes),
        games=library_games,
    )


def build_library_game_response(
    library_game: UserLibraryGame,
    game: Game | None,
) -> SteamLibraryGameResponse:
    return SteamLibraryGameResponse(
        steam_app_id=library_game.steam_app_id,
        game_id=None if game is None else game.id,
        title=get_library_game_title(library_game, game),
        image_url=None if game is None else game.image_url,
        genres=[] if game is None else list(game.genres),
        playtime_minutes=library_game.playtime_minutes,
        playtime_hours=minutes_to_hours(library_game.playtime_minutes),
        last_played_at=library_game.last_played_at,
        synced_at=library_game.synced_at,
        rating=None if game is None or game.review_score is None else float(game.review_score),
    )


def get_library_game_title(library_game: UserLibraryGame, game: Game | None) -> str:
    if game is not None:
        return game.title
    return f"Steam App {library_game.steam_app_id}"


def minutes_to_hours(minutes: int) -> float:
    return round(minutes / 60, 1)


async def reset_password(
    db: AsyncSession,
    request: PasswordResetRequest,
) -> None:
    email = request.email.lower()
    user = await get_user_by_email(db, email)
    if user is None:
        raise BadRequestException("가입되지 않은 이메일입니다.")
    if user.login_provider != LoginProvider.EMAIL or user.password_hash is None:
        raise BadRequestException("비밀번호 재설정을 사용할 수 없는 계정입니다.")
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenException("사용할 수 없는 계정입니다.")
    if not await consume_verified_email(email, EmailVerificationPurpose.PASSWORD_RESET):
        raise ForbiddenException("이메일 인증이 필요합니다.")

    user.password_hash = hash_password(request.password)
    await db.commit()
    await delete_all_refresh_tokens_for_user(user.id)


async def refresh_access_token(
    db: AsyncSession,
    response: Response,
    refresh_token: str,
) -> AccessTokenResponse:
    user_id = await validate_refresh_token(refresh_token)
    if user_id is None:
        raise UnauthorizedException("Refresh Token이 유효하지 않습니다.")

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise UnauthorizedException("사용자를 찾을 수 없습니다.")
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenException("사용할 수 없는 계정입니다.")

    await delete_refresh_token(refresh_token, user_id=user.id)
    auth_response = await issue_auth_tokens(response, user)
    return AccessTokenResponse(access_token=auth_response.access_token)


async def refresh_access_token_from_cookie(
    db: AsyncSession,
    response: Response,
    refresh_token: str | None,
) -> AccessTokenResponse:
    if refresh_token is None:
        raise UnauthorizedException("Refresh Token이 없습니다.")
    return await refresh_access_token(db, response, refresh_token)


async def logout_tokens(
    response: Response,
    access_token: str,
    refresh_token: str,
    user_id: int,
) -> None:
    await blacklist_access_token(access_token)
    await delete_refresh_token(refresh_token, user_id=user_id)
    delete_refresh_cookie(response)


async def logout_user(
    response: Response,
    access_token: str,
    refresh_token: str | None,
    user_id: int,
) -> MessageResponse:
    if refresh_token is not None:
        await logout_tokens(response, access_token, refresh_token, user_id)
    else:
        await blacklist_access_token(access_token)
        delete_refresh_cookie(response)

    return MessageResponse(message="로그아웃 되었습니다.")


async def withdraw_user(
    db: AsyncSession,
    response: Response,
    user_id: int,
    access_token: str,
    refresh_token: str | None,
    request: WithdrawRequest,
) -> WithdrawResponse:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise UnauthorizedException("사용자를 찾을 수 없습니다.")
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenException("이미 탈퇴했거나 사용할 수 없는 계정입니다.")

    if user.login_provider == LoginProvider.EMAIL:
        if user.password_hash is None or request.password is None:
            raise BadRequestException("비밀번호가 일치하지 않습니다.")
        if not verify_password(request.password, user.password_hash):
            raise BadRequestException("비밀번호가 일치하지 않습니다.")

    await delete_all_refresh_tokens_for_user(user.id)
    await blacklist_access_token(access_token)
    if refresh_token is not None:
        await delete_refresh_token(refresh_token, user_id=user.id)
    delete_refresh_cookie(response)

    await delete_user_by_id(db, user.id)
    await db.commit()
    return WithdrawResponse(message="회원 탈퇴가 완료되었습니다.")
