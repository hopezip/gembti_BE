from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 앱 기본 ───────────────────────────────────────────
    APP_NAME: str = "GEMBTI API"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = False

    # ── 데이터베이스 ──────────────────────────────────────
    DATABASE_URL: str  # postgresql+asyncpg://user:pw@host:5432/db  (async, FastAPI)
    DATABASE_SYNC_URL: str  # postgresql+psycopg2://user:pw@host:5432/db (sync, Celery/Alembic)

    # ── Redis ────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT / 인증 ────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    EMAIL_VERIFICATION_CODE_TTL_SECONDS: int = 300
    EMAIL_VERIFIED_TTL_SECONDS: int = 1800

    @property
    def REFRESH_TOKEN_TTL_SECONDS(self) -> int:
        return self.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    # ── CORS ─────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "https://gembti.cloud",
        "https://www.gembti.cloud",
    ]
    ALLOWED_ORIGIN_REGEX: str = r"https://.*\.vercel\.app"
    TRUSTED_HOSTS: list[str] = [
        "localhost",
        "127.0.0.1",
        "gembti.cloud",
        "www.gembti.cloud",
    ]

    # ── Rate Limit ───────────────────────────────────────
    RATE_LIMIT: str = "200/minute"

    # ── OpenAI ───────────────────────────────────────────
    OPENAI_API_KEY: str

    # ── AWS S3 ───────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-northeast-2"
    AWS_S3_BUCKET_NAME: str = ""
    AWS_S3_PRESIGNED_URL_EXPIRE: int = 3600  # seconds

    # ── Steam Web API ─────────────────────────────────────
    STEAM_API_KEY: str = ""

    # ── 이메일 (fastapi-mail) ─────────────────────────────
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_PORT: int = 587
    MAIL_SERVER: str = ""
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # ── Celery ───────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings loads from env


settings = get_settings()
