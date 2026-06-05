from types import SimpleNamespace
from typing import cast

from fastapi import Response
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.models import LoginProvider, User, UserStatus
from app.auth.schemas import AuthResponse, LoginRequest, UserResponse
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token


def create_user() -> User:
    return cast(
        "User",
        SimpleNamespace(
            id=7,
            email="test@example.com",
            password_hash="hashed",
            nickname="tester",
            bio=None,
            login_provider=LoginProvider.EMAIL,
            status=UserStatus.ACTIVE,
            steam_linked=False,
            steam_id_64=None,
            steam_avatar_url=None,
            steam_sync_status=None,
            last_synced_at=None,
        ),
    )


@pytest.mark.asyncio
async def test_issue_auth_tokens_returns_access_and_sets_refresh_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[int, str, str]] = []

    async def save_refresh_token(user_id: int, refresh_token: str, provider: str) -> str:
        saved.append((user_id, refresh_token, provider))
        return decode_token(refresh_token)["jti"]

    monkeypatch.setattr(service, "save_refresh_token", save_refresh_token)
    response = Response()

    token_response = await service.issue_auth_tokens(response=response, user=create_user())

    assert decode_token(token_response.access_token)["type"] == "access"
    assert decode_token(saved[0][1])["type"] == "refresh"
    assert saved[0][1] in response.headers["set-cookie"]
    assert token_response.user.steam_linked is False
    assert token_response.user.steam_sync_status is None
    assert not hasattr(token_response, "refresh_token")


@pytest.mark.asyncio
async def test_logout_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    blacklisted: list[str] = []
    deleted: list[tuple[str, int | None]] = []

    async def blacklist_access_token(token: str) -> bool:
        blacklisted.append(token)
        return True

    async def delete_refresh_token(token: str, user_id: int | None = None) -> None:
        deleted.append((token, user_id))

    monkeypatch.setattr(service, "blacklist_access_token", blacklist_access_token)
    monkeypatch.setattr(service, "delete_refresh_token", delete_refresh_token)
    response = Response()

    await service.logout_tokens(response, "access-token", "refresh-token", user_id=7)

    assert blacklisted == ["access-token"]
    assert deleted == [("refresh-token", 7)]
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_login_returns_tokens_for_valid_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    expected = AuthResponse(
        access_token="access-token",
        user=UserResponse.model_validate(user),
    )

    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        return user

    async def issue_auth_tokens(response: Response, user: User) -> AuthResponse:
        return expected

    monkeypatch.setattr(service, "get_user_by_email", get_user_by_email)
    monkeypatch.setattr(service, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(service, "issue_auth_tokens", issue_auth_tokens)

    result = await service.login(
        cast("AsyncSession", object()),
        Response(),
        LoginRequest(email="test@example.com", password="Password!1"),
    )

    assert result == expected


@pytest.mark.asyncio
async def test_login_hides_invalid_credential_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        return None

    monkeypatch.setattr(service, "get_user_by_email", get_user_by_email)

    with pytest.raises(UnauthorizedException, match="이메일 또는 비밀번호가 일치하지 않습니다."):
        await service.login(
            cast("AsyncSession", object()),
            Response(),
            LoginRequest(email="missing@example.com", password="Password!1"),
        )
