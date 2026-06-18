from fastapi import APIRouter, Body, Cookie, Depends, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    AccessTokenResponse,
    AuthResponse,
    EmailCodeSendRequest,
    EmailCodeVerifyRequest,
    LoginRequest,
    MessageResponse,
    NicknameCheckResponse,
    PasswordResetRequest,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    SignupRequest,
    UserActivityResponse,
    UserResponse,
    WithdrawRequest,
    WithdrawResponse,
)
from app.auth.service import (
    check_nickname_available,
    get_me,
    get_my_activity,
    login,
    logout_user,
    refresh_access_token_from_cookie,
    reset_password,
    send_email_code,
    signup,
    update_me,
    verify_email,
    withdraw_user,
)
from app.core.config import settings
from app.core.dependencies import bearer_scheme, get_current_user_id, get_db
from app.core.exceptions import UnauthorizedException

router = APIRouter(prefix="/auth", tags=["Auth"])

_err = lambda msg: {"content": {"application/json": {"example": {"error": msg}}}}  # noqa: E731


@router.post(
    "/email/send-code",
    response_model=MessageResponse,
    responses={
        400: _err("잘못된 이메일 형식"),
        409: _err("이미 가입된 이메일입니다."),
        429: _err("요청 횟수가 너무 많습니다. 잠시 후 다시 시도해주세요."),
    },
)
async def send_email_code_api(
    request: EmailCodeSendRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await send_email_code(db, request.email, request.purpose)
    return MessageResponse(message="인증번호를 발송했습니다.")


@router.post(
    "/email/verify",
    response_model=MessageResponse,
    responses={
        400: _err("인증번호가 만료되었거나 일치하지 않습니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def verify_email_api(request: EmailCodeVerifyRequest) -> MessageResponse:
    await verify_email(request.email, request.purpose, request.code)
    return MessageResponse(message="이메일 인증이 완료되었습니다.")


@router.get(
    "/nickname/check",
    response_model=NicknameCheckResponse,
    responses={
        400: _err("닉네임 형식이 올바르지 않습니다."),
        409: _err("이미 사용 중인 닉네임입니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def check_nickname_api(
    nickname: str = Query(),
    db: AsyncSession = Depends(get_db),
) -> NicknameCheckResponse:
    return await check_nickname_available(db, nickname)


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: _err("이메일 인증이 필요합니다."),
        409: _err("이미 사용 중인 이메일입니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def signup_api(
    request: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await signup(db, response, request)


@router.post(
    "/login",
    response_model=AccessTokenResponse,
    responses={
        401: _err("이메일 또는 비밀번호가 일치하지 않습니다."),
        403: _err("사용할 수 없는 계정입니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def login_api(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    return await login(db, response, request)


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    responses={
        400: _err("가입되지 않은 이메일입니다."),
        403: _err("이메일 인증이 필요합니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def reset_password_api(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await reset_password(db, request)
    return MessageResponse(message="비밀번호가 재설정되었습니다.")


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    responses={
        401: _err("Refresh Token이 없거나 유효하지 않습니다."),
        403: _err("사용할 수 없는 계정입니다."),
    },
)
async def refresh_api(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    return await refresh_access_token_from_cookie(db, response, refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    responses={
        400: _err("잘못된 요청입니다."),
        409: _err("이미 로그아웃된 토큰입니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def logout_api(
    response: Response,
    user_id: int = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
) -> MessageResponse:
    if credentials is None:
        raise UnauthorizedException()

    return await logout_user(response, credentials.credentials, refresh_token, user_id)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: _err("인증 실패"),
        404: _err("사용자를 찾을 수 없습니다."),
    },
)
async def me_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    return await get_me(db, user_id)


@router.patch(
    "/profile",
    response_model=ProfileUpdateResponse,
    responses={
        400: _err("수정할 프로필 항목이 필요합니다."),
        401: _err("인증 실패"),
        404: _err("사용자를 찾을 수 없습니다."),
        409: _err("이미 사용 중인 닉네임입니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def update_me_api(
    request: ProfileUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProfileUpdateResponse:
    """현재 사용자 프로필 수정 요청을 서비스 계층으로 위임한다.

    FastAPI가 request body 검증, 로그인 사용자 식별, DB 세션 주입을 처리하고,
    닉네임 중복 확인과 실제 프로필 수정은 service.update_me에서 담당한다.
    """
    return await update_me(db, user_id, request)


@router.get(
    "/me/activity",
    response_model=UserActivityResponse,
    responses={
        401: _err("인증 실패"),
        404: _err("사용자를 찾을 수 없습니다."),
    },
)
async def my_activity_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserActivityResponse:
    return await get_my_activity(db, user_id)


@router.delete(
    "/withdrawal",
    response_model=WithdrawResponse,
    responses={
        400: _err("비밀번호가 일치하지 않습니다."),
        401: _err("인증 실패"),
        403: _err("탈퇴 처리할 수 없는 계정입니다."),
        422: _err("요청 형식이 올바르지 않습니다."),
    },
)
async def withdraw_me_api(
    response: Response,
    request: WithdrawRequest = Body(default_factory=WithdrawRequest),
    user_id: int = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> WithdrawResponse:
    if credentials is None:
        raise UnauthorizedException()

    return await withdraw_user(
        db=db,
        response=response,
        user_id=user_id,
        access_token=credentials.credentials,
        refresh_token=refresh_token,
        request=request,
    )
