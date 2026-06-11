from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middlewares import register_middlewares
from app.core.redis import close_redis
from app.game.router import router as game_router
from app.steam.router import router as steam_router
from app.survey.router import router as survey_router
from app.recommend.router import router as recommend_router


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



    API_PREFIX = "/api/v1"
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(survey_router, prefix=API_PREFIX)
    # app.include_router(stat_router, prefix=API_PREFIX)
    app.include_router(recommend_router, prefix=API_PREFIX)
    app.include_router(game_router, prefix=API_PREFIX)
    app.include_router(steam_router, prefix=API_PREFIX)

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        error_schema = {
            "title": "ErrorResponse",
            "type": "object",
            "properties": {"error": {"title": "Error", "type": "string"}},
            "required": ["error"],
        }
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components["ErrorResponse"] = error_schema
        components.pop("HTTPValidationError", None)
        components.pop("ValidationError", None)
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                responses = operation.get("responses", {})
                for code in ("422", "404", "400", "401", "403", "409", "500"):
                    if code in responses:
                        responses[code]["content"] = {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    return app


app = create_app()
