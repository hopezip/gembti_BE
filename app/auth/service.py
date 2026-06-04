import secrets

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookie import delete_refresh_cookie, set_refresh_cookie
from app.auth.email_sender import send_verification_email
from app.auth.email_verification_store import (
    consume_verified_email,
    delete_verification_code,
    save_verification_code,
    verify_email_code,
)
from app.auth.models import EmailVerificationPurpose, LoginProvider, User, UserStatus
from app.auth.refresh_store import delete_refresh_token, save_refresh_token, validate_refresh_token
from app.auth.repository import (
    get_user_by_email,
    get_user_by_id,
    get_user_by_nickname,
    save_user,
)
from app.auth.schemas import (
    AccessTokenResponse,
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UserResponse,
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


async def issue_auth_tokens(
    response: Response,
    user: User,
) -> AuthResponse:
    provider = user.login_provider.value
    access_token = create_access_token(subject=user.id, provider=provider)
    refresh_token = create_refresh_token(subject=user.id, provider=provider)
    await save_refresh_token(user.id, refresh_token, provider)
    set_refresh_cookie(response, refresh_token)

    return AuthResponse(access_token=access_token, user=UserResponse.model_validate(user))


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
