# ── 빌드 스테이지 ─────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

# .venv에 의존성만 설치 (프로젝트 소스 제외)
RUN uv sync --frozen --no-dev --no-install-project

# ── 런타임 스테이지 ───────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# 보안: 전용 유저 생성
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# 빌드 스테이지의 .venv만 복사
COPY --from=builder /app/.venv /app/.venv

# 소스 복사
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# .venv/bin을 PATH 앞에 추가
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
