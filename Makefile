.PHONY: lint test ci infra-up infra-down

# ── 테스트 환경변수 ──────────────────────────────────────────
export APP_ENV               = test
export DEBUG                 = False
export DATABASE_URL          = postgresql+asyncpg://gembti:gembti@localhost:5432/gembti_test
export DATABASE_SYNC_URL     = postgresql+psycopg2://gembti:gembti@localhost:5432/gembti_test
export REDIS_URL             = redis://localhost:6379/0
export SECRET_KEY            = test-secret-key-for-ci-only
export OPENAI_API_KEY        = sk-test-placeholder
export CELERY_BROKER_URL     = redis://localhost:6379/1
export CELERY_RESULT_BACKEND = redis://localhost:6379/2
export TRUSTED_HOSTS         = ["localhost","127.0.0.1","testserver"]

# ── 인프라 ──────────────────────────────────────────────────
infra-up:
	docker compose -f docker-compose.infra.yml up -d
	@echo "Waiting for postgres..."
	@until docker exec gembti_postgres pg_isready -U gembti > /dev/null 2>&1; do sleep 1; done
	@docker exec gembti_postgres psql -U gembti -tc \
		"SELECT 1 FROM pg_database WHERE datname='gembti_test'" \
		| grep -q 1 || docker exec gembti_postgres psql -U gembti -c "CREATE DATABASE gembti_test"

infra-down:
	docker compose -f docker-compose.infra.yml down

# ── lint ─────────────────────────────────────────────────────
lint:
	uv run ruff check .
	uv run isort --check-only .
	uv run black --check .
	uv run mypy app/

# ── test ─────────────────────────────────────────────────────
test: infra-up
	uv run alembic upgrade head
	uv run pytest --cov=app --cov-report=xml

# ── ci = lint + test ─────────────────────────────────────────
ci: lint test
