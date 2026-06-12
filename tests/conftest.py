import os

from httpx import ASGITransport, AsyncClient
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base
from app.core.dependencies import get_db
from app.main import app


# Docker 내부 호스트명(postgres) → localhost 치환, DB명 → gembti_test
def _test_db_url() -> str:
    base = settings.DATABASE_URL.replace("@postgres:", "@localhost:")
    prefix, _ = base.rsplit("/", 1)  # 마지막 /로 분리해서 DB명만 교체
    return f"{prefix}/gembti_test"


_DB_URL = os.getenv("TEST_DATABASE_URL", _test_db_url())


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """세션 전체에서 공유하는 DB 엔진. 테이블 생성 → 테스트 → 삭제."""
    engine = create_async_engine(_DB_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(test_engine):
    """각 테스트마다 독립적인 세션. 종료 시 rollback."""
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client():
    """DB 없이 사용하는 기본 테스트 클라이언트."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        yield ac
