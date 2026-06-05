from fastapi import Response
import pytest

from app.auth import service
from app.core.security import decode_token


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

    token_response = await service.issue_auth_tokens(
        response=response,
        user_id=7,
        provider="email",
    )

    assert decode_token(token_response.access_token)["type"] == "access"
    assert decode_token(saved[0][1])["type"] == "refresh"
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
