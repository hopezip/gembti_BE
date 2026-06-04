from fastapi import Depends
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.dependencies import get_current_user_id
from app.core.security import create_access_token, create_refresh_token
from app.main import app


@pytest.fixture(autouse=True, scope="module")
def register_test_route():
    @app.get("/me-test")
    async def me(user_id: int = Depends(get_current_user_id)):
        return JSONResponse({"user_id": user_id})


@pytest.mark.asyncio
async def test_valid_access_token():
    token = create_access_token(subject=7)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        r = await ac.get("/me-test", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user_id"] == 7


@pytest.mark.asyncio
async def test_no_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        r = await ac.get("/me-test")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        r = await ac.get("/me-test", headers={"Authorization": "Bearer invalid.token.here"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rejected():
    token = create_refresh_token(subject=7)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        r = await ac.get("/me-test", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
