from datetime import UTC, datetime, timedelta
import secrets

from fastapi import Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.auth.email_sender import send_verification_email
from app.auth.email_verification_store import (
    consume_verified_email,
    delete_verification_code,
    save_verification_code,
    verify_email_code,
)
from app.auth.models import (
    EmailVerificationPurpose,
    LoginProvider,
    User,
    UserStatus,
    UserWithdrawalRequest,
    UserWithdrawalStatus,
)
from app.auth.refresh_store import (
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    save_refresh_token,
    validate_refresh_token,
)
from app.auth.repository import (
    get_expired_withdrawal_requests,
    get_requested_withdrawal_by_user_id,
    get_user_by_email,
    get_user_by_id,
    get_user_by_nickname,
    save_user,
)
from app.auth.schemas import (
    AccessTokenResponse,
    AuthResponse,
    LoginRequest,
    NicknameCheckResponse,
    PasswordResetRequest,
    SignupRequest,
    WithdrawRequest,
    WithdrawResponse,
)
from app.auth.token_blacklist import blacklist_access_token
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.steam.models import SteamAccount, UserLibraryGame

WITHDRAWAL_GRACE_PERIOD_DAYS = 14


async def issue_auth_tokens(
    response: Response,
    user: User,
) -> AuthResponse:
    provider = user.login_provider.value
    access_token = create_access_token(subject=user.id, provider=provider)
    refresh_token = create_refresh_token(subject=user.id, provider=provider)
    await save_refresh_token(user.id, refresh_token, provider)
    set_refresh_cookie(response, refresh_token)

    return AuthResponse(access_token=access_token)


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
) -> AuthResponse:
    user = await get_user_by_email(db, request.email.lower())

    if (
        user is None
        or user.password_hash is None
        or not verify_password(request.password, user.password_hash)
    ):
        raise UnauthorizedException("이메일 또는 비밀번호가 일치하지 않습니다.")
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenException("사용할 수 없는 계정입니다.")

    return await issue_auth_tokens(response, user)


async def check_nickname_available(
    db: AsyncSession,
    nickname: str,
) -> NicknameCheckResponse:
    if await get_user_by_nickname(db, nickname):
        return NicknameCheckResponse(
            available=False,
            message="이미 사용 중인 닉네임입니다.",
        )

    return NicknameCheckResponse(
        available=True,
        message="사용 가능한 닉네임입니다.",
    )


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


async def logout_tokens(
    response: Response,
    access_token: str,
    refresh_token: str,
    user_id: int,
) -> None:
    await blacklist_access_token(access_token)
    await delete_refresh_token(refresh_token, user_id=user_id)
    delete_refresh_cookie(response)


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

    if await get_requested_withdrawal_by_user_id(db, user.id):
        raise ForbiddenException("이미 탈퇴했거나 사용할 수 없는 계정입니다.")

    now = datetime.now(UTC)
    hard_delete_after = now + timedelta(days=WITHDRAWAL_GRACE_PERIOD_DAYS)

    user.status = UserStatus.WITHDRAWN
    user.withdrawn_at = now
    user.hard_delete_after = hard_delete_after

    db.add(
        UserWithdrawalRequest(
            user_id=user.id,
            reason=request.reason,
            detail=request.detail,
            hard_delete_after=hard_delete_after,
        )
    )
    await db.commit()

    await delete_all_refresh_tokens_for_user(user.id)
    await blacklist_access_token(access_token)
    if refresh_token is not None:
        await delete_refresh_token(refresh_token, user_id=user.id)
    delete_refresh_cookie(response)

    return WithdrawResponse(
        message="회원 탈퇴 요청이 완료되었습니다.",
        hard_delete_after=hard_delete_after,
    )


async def cleanup_expired_withdrawn_users(
    db: AsyncSession,
    now: datetime | None = None,
) -> int:
    cleanup_time = now or datetime.now(UTC)
    withdrawal_requests = await get_expired_withdrawal_requests(db, cleanup_time)

    for withdrawal_request in withdrawal_requests:
        user = withdrawal_request.user
        user.email = f"deleted_{user.id}@deleted.local"
        user.nickname = f"deleted_user_{user.id}"
        user.password_hash = None
        user.bio = None
        user.gender = None
        user.birth_date = None
        user.status = UserStatus.DELETED
        user.deleted_at = cleanup_time

        withdrawal_request.status = UserWithdrawalStatus.HARD_DELETED
        withdrawal_request.hard_deleted_at = cleanup_time

        await db.execute(delete(SteamAccount).where(SteamAccount.user_id == user.id))
        await db.execute(delete(UserLibraryGame).where(UserLibraryGame.user_id == user.id))
        await delete_all_refresh_tokens_for_user(user.id)

    await db.commit()
    return len(withdrawal_requests)
