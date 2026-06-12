from types import SimpleNamespace
from typing import cast

from fastapi import Response
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.models import LoginProvider, User, UserStatus, UserWithdrawalStatus
from app.auth.schemas import AuthResponse, LoginRequest, PasswordResetRequest, WithdrawRequest
from app.core.exceptions import BadRequestException, ForbiddenException, UnauthorizedException
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
    expected = AuthResponse(access_token="access-token", user=user)

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


@pytest.mark.asyncio
async def test_check_nickname_available_returns_false_for_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_user_by_nickname(db: AsyncSession, nickname: str) -> User | None:
        return create_user()

    monkeypatch.setattr(service, "get_user_by_nickname", get_user_by_nickname)

    result = await service.check_nickname_available(
        cast("AsyncSession", object()),
        "tester",
    )

    assert result.available is False
    assert result.message == "이미 사용 중인 닉네임입니다."


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
async def test_withdraw_user_soft_deletes_and_clears_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    added: list[object] = []
    committed: list[bool] = []
    deleted_all: list[int] = []
    blacklisted: list[str] = []
    deleted_refresh: list[tuple[str, int | None]] = []

    class FakeSession:
        def add(self, value: object) -> None:
            added.append(value)

        async def commit(self) -> None:
            committed.append(True)

    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        return user

    async def get_requested_withdrawal_by_user_id(db: AsyncSession, user_id: int):
        return None

    async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
        deleted_all.append(user_id)

    async def blacklist_access_token(token: str) -> bool:
        blacklisted.append(token)
        return True

    async def delete_refresh_token(token: str, user_id: int | None = None) -> None:
        deleted_refresh.append((token, user_id))

    monkeypatch.setattr(service, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(
        service,
        "get_requested_withdrawal_by_user_id",
        get_requested_withdrawal_by_user_id,
    )
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
        request=WithdrawRequest(password="Password!1", reason="reason"),
    )

    assert user.status == UserStatus.WITHDRAWN
    assert user.withdrawn_at is not None
    assert user.hard_delete_after == result.hard_delete_after
    assert added
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
async def test_cleanup_expired_withdrawn_users_anonymizes_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user()
    user.status = UserStatus.WITHDRAWN
    withdrawal_request = SimpleNamespace(
        user=user,
        status=UserWithdrawalStatus.REQUESTED,
        hard_deleted_at=None,
    )
    executed: list[object] = []
    committed: list[bool] = []
    deleted_all: list[int] = []

    class FakeSession:
        async def execute(self, statement: object) -> None:
            executed.append(statement)

        async def commit(self) -> None:
            committed.append(True)

    async def get_expired_withdrawal_requests(db: AsyncSession, now):
        return [withdrawal_request]

    async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
        deleted_all.append(user_id)

    monkeypatch.setattr(
        service,
        "get_expired_withdrawal_requests",
        get_expired_withdrawal_requests,
    )
    monkeypatch.setattr(
        service,
        "delete_all_refresh_tokens_for_user",
        delete_all_refresh_tokens_for_user,
    )

    count = await service.cleanup_expired_withdrawn_users(cast("AsyncSession", FakeSession()))

    assert count == 1
    assert user.status == UserStatus.DELETED
    assert user.email == "deleted_7@deleted.local"
    assert user.nickname == "deleted_user_7"
    assert user.password_hash is None
    assert user.deleted_at is not None
    assert withdrawal_request.status == UserWithdrawalStatus.HARD_DELETED
    assert withdrawal_request.hard_deleted_at is not None
    assert len(executed) == 2
    assert committed == [True]
    assert deleted_all == [7]
