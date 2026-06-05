from fastapi import Response
import pytest

from app.auth import service
from app.core.security import decode_token


def test_issue_auth_tokens_returns_access_and_sets_refresh_cookie() -> None:
    response = Response()

    token_response, refresh_token = service.issue_auth_tokens(
        response=response,
        user_id=7,
        provider="email",
    )

    assert decode_token(token_response.access_token)["type"] == "access"
    assert decode_token(refresh_token)["type"] == "refresh"
    assert refresh_token in response.headers["set-cookie"]
    assert not hasattr(token_response, "refresh_token")


@pytest.mark.asyncio
async def test_logout_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    blacklisted: list[str] = []

    async def blacklist_access_token(token: str) -> bool:
        blacklisted.append(token)
        return True

    monkeypatch.setattr(service, "blacklist_access_token", blacklist_access_token)
    response = Response()

    await service.logout_access_token(response, "access-token")

    assert blacklisted == ["access-token"]
    assert "Max-Age=0" in response.headers["set-cookie"]
