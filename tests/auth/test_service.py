from types import SimpleNamespace
from typing import cast

from fastapi import Response
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.models import User
from app.auth.schemas import (
    AccessTokenResponse,
    AuthResponse,
    AuthUserResponse,
    LoginRequest,
    PasswordResetRequest,
    UserFlowStatus,
    WithdrawRequest,
)
from app.core.enums import LoginProvider, UserStatus
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
)
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
            gender=None,
            birth_date=None,
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
    assert token_response.user.id == 7
    assert saved[0][1] in response.headers["set-cookie"]
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
    expected = AuthResponse(access_token="access-token", user=AuthUserResponse.model_validate(user))

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

    assert result == AccessTokenResponse(access_token=expected.access_token)


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


@pytest.mark.asyncio
async def test_check_nickname_available_raises_conflict_for_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_user_by_nickname(db: AsyncSession, nickname: str) -> User | None:
        return create_user()

    monkeypatch.setattr(service, "get_user_by_nickname", get_user_by_nickname)

    with pytest.raises(ConflictException, match="이미 사용 중인 닉네임입니다."):
        await service.check_nickname_available(
            cast("AsyncSession", object()),
            "tester",
        )


@pytest.mark.asyncio
async def test_check_nickname_available_raises_bad_request_for_invalid_format() -> None:
    with pytest.raises(BadRequestException, match="닉네임 형식이 올바르지 않습니다."):
        await service.check_nickname_available(
            cast("AsyncSession", object()),
            "ㄱㅁㄷ",
        )


@pytest.mark.asyncio
async def test_check_nickname_available_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_user_by_nickname(db: AsyncSession, nickname: str) -> User | None:
        return None

    monkeypatch.setattr(service, "get_user_by_nickname", get_user_by_nickname)

    result = await service.check_nickname_available(
        cast("AsyncSession", object()),
        "tester",
    )

    assert result.available is True
    assert result.message == "사용 가능한 닉네임입니다."


@pytest.mark.asyncio
async def test_get_me_returns_user_flow_status_for_completed_survey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    async def has_user_stats(db: AsyncSession, user_id: int) -> bool:
        return True

    async def get_user_steam_library_rows(db: AsyncSession, user_id: int):
        return []

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "has_user_stats", has_user_stats)
    monkeypatch.setattr(
        service,
        "get_user_steam_library_rows",
        get_user_steam_library_rows,
    )

    result = await service.get_me(cast("AsyncSession", object()), user_id=7)

    assert result.id == 7
    assert result.user_id == 7
    assert result.email == "test@example.com"
    assert result.nickname == "tester"
    assert result.has_completed_survey is True
    assert result.user_flow_status == UserFlowStatus.READY
    assert result.steam_library.library_game_count == 0
    assert result.steam_library.total_playtime_minutes == 0
    assert result.steam_library.games == []


@pytest.mark.asyncio
async def test_get_me_returns_needs_survey_without_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    async def has_user_stats(db: AsyncSession, user_id: int) -> bool:
        return False

    async def get_user_steam_library_rows(db: AsyncSession, user_id: int):
        return []

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "has_user_stats", has_user_stats)
    monkeypatch.setattr(
        service,
        "get_user_steam_library_rows",
        get_user_steam_library_rows,
    )

    result = await service.get_me(cast("AsyncSession", object()), user_id=7)

    assert result.has_completed_survey is False
    assert result.user_flow_status == UserFlowStatus.NEEDS_SURVEY


@pytest.mark.asyncio
async def test_reset_password_updates_hash_and_clears_refresh_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    committed: list[bool] = []
    deleted_all: list[int] = []

    class FakeSession:
        async def commit(self) -> None:
            committed.append(True)

    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        return user

    async def consume_verified_email(email, purpose) -> bool:
        return True

    async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
        deleted_all.append(user_id)

    monkeypatch.setattr(service, "get_user_by_email", get_user_by_email)
    monkeypatch.setattr(service, "consume_verified_email", consume_verified_email)
    monkeypatch.setattr(service, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(
        service,
        "delete_all_refresh_tokens_for_user",
        delete_all_refresh_tokens_for_user,
    )

    await service.reset_password(
        cast("AsyncSession", FakeSession()),
        PasswordResetRequest(
            email="TEST@example.com",
            password="NewPassword!1",
            password_confirm="NewPassword!1",
        ),
    )

    assert user.password_hash == "hashed:NewPassword!1"
    assert committed == [True]
    assert deleted_all == [7]


@pytest.mark.asyncio
async def test_reset_password_requires_verified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()

    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        return user

    async def consume_verified_email(email, purpose) -> bool:
        return False

    monkeypatch.setattr(service, "get_user_by_email", get_user_by_email)
    monkeypatch.setattr(service, "consume_verified_email", consume_verified_email)

    with pytest.raises(ForbiddenException, match="이메일 인증이 필요합니다."):
        await service.reset_password(
            cast("AsyncSession", object()),
            PasswordResetRequest(
                email="test@example.com",
                password="NewPassword!1",
                password_confirm="NewPassword!1",
            ),
        )


@pytest.mark.asyncio
async def test_withdraw_user_hard_deletes_and_clears_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    committed: list[bool] = []
    deleted_users: list[int] = []
    deleted_all: list[int] = []
    blacklisted: list[str] = []
    deleted_refresh: list[tuple[str, int | None]] = []

    class FakeSession:
        async def commit(self) -> None:
            committed.append(True)

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    async def delete_user_by_id(db: AsyncSession, user_id: int) -> None:
        deleted_users.append(user_id)

    async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
        deleted_all.append(user_id)

    async def blacklist_access_token(token: str) -> bool:
        blacklisted.append(token)
        return True

    async def delete_refresh_token(token: str, user_id: int | None = None) -> None:
        deleted_refresh.append((token, user_id))

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "delete_user_by_id", delete_user_by_id)
    monkeypatch.setattr(service, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(
        service,
        "delete_all_refresh_tokens_for_user",
        delete_all_refresh_tokens_for_user,
    )
    monkeypatch.setattr(service, "blacklist_access_token", blacklist_access_token)
    monkeypatch.setattr(service, "delete_refresh_token", delete_refresh_token)

    response = Response()
    result = await service.withdraw_user(
        db=cast("AsyncSession", FakeSession()),
        response=response,
        user_id=7,
        access_token="access-token",
        refresh_token="refresh-token",
        request=WithdrawRequest(password="Password!1"),
    )

    assert result.message == "회원 탈퇴가 완료되었습니다."
    assert deleted_users == [7]
    assert committed == [True]
    assert deleted_all == [7]
    assert blacklisted == ["access-token"]
    assert deleted_refresh == [("refresh-token", 7)]
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_withdraw_user_requires_email_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)

    with pytest.raises(BadRequestException, match="비밀번호가 일치하지 않습니다."):
        await service.withdraw_user(
            db=cast("AsyncSession", object()),
            response=Response(),
            user_id=7,
            access_token="access-token",
            refresh_token=None,
            request=WithdrawRequest(),
        )


@pytest.mark.asyncio
async def test_withdraw_steam_user_does_not_require_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    user.login_provider = LoginProvider.STEAM
    user.password_hash = None
    deleted_users: list[int] = []

    class FakeSession:
        async def commit(self) -> None:
            return None

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    async def delete_user_by_id(db: AsyncSession, user_id: int) -> None:
        deleted_users.append(user_id)

    async def no_op(*args: object, **kwargs: object) -> None:
        return None

    async def blacklist_access_token(token: str) -> bool:
        return True

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(service, "delete_user_by_id", delete_user_by_id)
    monkeypatch.setattr(service, "delete_all_refresh_tokens_for_user", no_op)
    monkeypatch.setattr(service, "delete_refresh_token", no_op)
    monkeypatch.setattr(service, "blacklist_access_token", blacklist_access_token)

    result = await service.withdraw_user(
        db=cast("AsyncSession", FakeSession()),
        response=Response(),
        user_id=7,
        access_token="access-token",
        refresh_token=None,
        request=WithdrawRequest(),
    )

    assert result.message == "회원 탈퇴가 완료되었습니다."
    assert deleted_users == [7]
