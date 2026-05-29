from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
    register_exception_handlers,
)


def make_app_with_route(exc: Exception) -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/trigger")
    async def trigger():
        raise exc

    return test_app


@pytest.mark.asyncio
async def test_not_found():
    app = make_app_with_route(NotFoundException("게임 없음"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/trigger")
    assert r.status_code == 404
    assert r.json()["detail"] == "게임 없음"


@pytest.mark.asyncio
async def test_unauthorized():
    app = make_app_with_route(UnauthorizedException())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/trigger")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_forbidden():
    app = make_app_with_route(ForbiddenException())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/trigger")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bad_request():
    app = make_app_with_route(BadRequestException("잘못된 형식"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/trigger")
    assert r.status_code == 400
    assert r.json()["detail"] == "잘못된 형식"


@pytest.mark.asyncio
async def test_conflict():
    app = make_app_with_route(ConflictException())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/trigger")
    assert r.status_code == 409
