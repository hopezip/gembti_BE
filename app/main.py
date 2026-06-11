from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.core import model_registry as model_registry
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middlewares import register_middlewares
from app.core.redis import close_redis
from app.game.router import router as game_router
from app.steam.router import router as steam_router
from app.survey.router import router as survey_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
    )

    register_middlewares(app)
    register_exception_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # ── 라우터 등록 (각 모듈 완성 후 주석 해제) ──────────────
    # from app.stat.router import router as stat_router
    from app.recommend.router import router as recommend_router

    # from app.survey.router import router as survey_router

    # from app.support.router import router as support_router
    # from app.chat.router import router as chat_router

    API_PREFIX = "/api/v1"
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(survey_router, prefix=API_PREFIX)
    # app.include_router(stat_router, prefix=API_PREFIX)
    app.include_router(recommend_router, prefix=API_PREFIX)
    app.include_router(game_router, prefix=API_PREFIX)
    app.include_router(steam_router, prefix=API_PREFIX)
    # app.include_router(support_router, prefix=API_PREFIX)
    # app.include_router(chat_router, prefix=API_PREFIX)

    return app


app = create_app()
