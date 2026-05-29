"""루트 conftest — tests/conftest.py 보다 먼저 실행되어 앱 임포트 전에 환경변수를 주입합니다."""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://gembti:gembti@localhost:5432/gembti_test"
)
os.environ.setdefault(
    "DATABASE_SYNC_URL", "postgresql+psycopg2://gembti:gembti@localhost:5432/gembti_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
