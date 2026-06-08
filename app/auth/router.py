from fastapi import APIRouter, Body, Cookie, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookie import delete_refresh_cookie
from app.auth.repository import get_user_by_id, has_user_stats
from app.auth.schemas import (
    AccessTokenResponse,
    AuthResponse,
    EmailCodeSendRequest,
    EmailCodeVerifyRequest,
    LoginRequest,
    MessageResponse,
    SignupRequest,
    UserFlowStatus,
    UserResponse,
    WithdrawRequest,
    WithdrawResponse,
)
from app.auth.service import (
    login,
    logout_tokens,
    refresh_access_token,
    send_email_code,
    signup,
    verify_email,
    withdraw_user,
)
from app.auth.token_blacklist import blacklist_access_token
from app.core.config import settings
from app.core.dependencies import bearer_scheme, get_current_user_id, get_db
from app.core.exceptions import NotFoundException, UnauthorizedException

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/email/send-code", response_model=MessageResponse)
async def send_email_code_api(
    request: EmailCodeSendRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await send_email_code(db, request.email, request.purpose)
    return MessageResponse(message="인증번호를 발송했습니다.")


@router.post("/email/verify", response_model=MessageResponse)
async def verify_email_api(request: EmailCodeVerifyRequest) -> MessageResponse:
    await verify_email(request.email, request.purpose, request.code)
    return MessageResponse(message="이메일 인증이 완료되었습니다.")


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup_api(
    request: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await signup(db, response, request)


@router.post("/login", response_model=AuthResponse)
async def login_api(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await login(db, response, request)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_api(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    if refresh_token is None:
        raise UnauthorizedException("Refresh Token이 없습니다.")
    return await refresh_access_token(db, response, refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_api(
    response: Response,
    user_id: int = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
) -> None:
    if credentials is None:
        raise UnauthorizedException()

    if refresh_token is not None:
        await logout_tokens(response, credentials.credentials, refresh_token, user_id)
    else:
        await blacklist_access_token(credentials.credentials)
        delete_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me_api(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundException("사용자를 찾을 수 없습니다.")

    user_data = UserResponse.model_validate(user).model_dump(
        exclude={"has_completed_survey", "user_flow_status"}
    )
    has_completed_survey = await has_user_stats(db, user.id)
    return UserResponse(
        **user_data,
        has_completed_survey=has_completed_survey,
        user_flow_status=(
            UserFlowStatus.READY if has_completed_survey else UserFlowStatus.NEEDS_SURVEY
        ),
    )


@router.delete("/me", response_model=WithdrawResponse)
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
