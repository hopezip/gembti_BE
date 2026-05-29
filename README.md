# GEMBTI Backend

게임 성향 기반 추천 서비스 백엔드 API

---

## 목차

1. [기술 스택](#기술-스택)
2. [프로젝트 구조](#프로젝트-구조)
3. [로컬 개발 환경](#로컬-개발-환경)
4. [환경변수](#환경변수)
5. [Docker 세팅](#docker-세팅)
6. [데이터베이스 마이그레이션](#데이터베이스-마이그레이션)
7. [테스트](#테스트)
8. [CI/CD 파이프라인](#cicd-파이프라인)
9. [AWS 서버 세팅](#aws-서버-세팅)

---

## 기술 스택

| 분류 | 기술 |
|---|---|
| 웹 프레임워크 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| DB | PostgreSQL 16 + pgvector |
| 캐시 / 브로커 | Redis 7 |
| 비동기 작업 | Celery |
| 인증 | JWT (python-jose) + bcrypt |
| 레이트 리밋 | slowapi |
| AI | OpenAI API |
| 패키지 관리 | uv |
| 컨테이너 | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| 서버 | AWS EC2 (Ubuntu 24.04) |

---

## 프로젝트 구조

```
gembti_BE/
├── app/
│   ├── main.py              # FastAPI 앱 팩토리, lifespan
│   ├── core/
│   │   ├── config.py        # 환경변수 (pydantic-settings)
│   │   ├── database.py      # 비동기 SQLAlchemy 엔진 + Base
│   │   ├── redis.py         # Redis 클라이언트
│   │   ├── security.py      # bcrypt + JWT
│   │   ├── dependencies.py  # get_db(), get_current_user_id()
│   │   ├── exceptions.py    # 공통 예외 클래스 + 핸들러
│   │   ├── middlewares.py   # CORS + slowapi 레이트 리밋
│   │   └── celery_app.py    # Celery 인스턴스
│   ├── auth/                # 회원가입, 로그인, Steam 연동
│   ├── survey/              # 설문조사
│   ├── stat/                # 성향 분석
│   ├── recommend/           # 게임 추천
│   ├── game/                # 게임 정보
│   ├── steam/               # Steam 데이터 동기화
│   ├── support/             # 고객센터 챗봇
│   ├── chat/                # 설문 챗봇
│   ├── chat_common/         # 챗봇 공통
│   └── common/              # 공통 유틸
├── alembic/
│   ├── env.py               # DB URL 자동 주입, 모델 import
│   ├── script.py.mako       # 마이그레이션 파일 템플릿
│   └── versions/            # 마이그레이션 파일
├── nginx/
│   ├── Dockerfile           # Nginx 독립 이미지
│   └── conf.d/default.conf  # 리버스 프록시 설정
├── scripts/
│   ├── ec2_setup.sh         # EC2 초기 세팅 스크립트
│   └── iam_policy.json      # GitHub Actions용 IAM 정책
├── tests/
│   ├── conftest.py          # DB / 클라이언트 픽스처
│   ├── test_config.py
│   ├── test_security.py
│   ├── test_exceptions.py
│   ├── test_dependencies.py
│   └── test_health.py
├── docs/help/support/       # 고객센터 RAG 도움말 문서
├── .github/workflows/
│   ├── ci.yml               # lint + test (모든 브랜치 push / PR)
│   ├── cd_dev.yml           # develop PR merge → 개발 EC2 배포
│   └── cd_prod.yml          # main PR merge → 운영 서버 배포
├── conftest.py              # 테스트 환경변수 주입 (루트)
├── Dockerfile               # 멀티스테이지 빌드
├── docker-compose.yml       # 로컬 / 개발 서버 공통
├── docker-compose.dev.yml   # 로컬 개발 오버라이드 (핫리로드)
├── alembic.ini
├── pyproject.toml
└── .env.example
```

---

## 로컬 개발 환경

### 사전 요구사항

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop

### 설치 및 실행

```bash
# 1. 저장소 클론
git clone <repo-url> && cd gembti_BE

# 2. 환경변수 설정
cp .env.example .env
# .env 수정

# 3. 의존성 설치
uv sync

# 4. 전체 서비스 실행 (핫리로드 포함)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# 5. DB 마이그레이션
docker compose exec app alembic upgrade head
```

서비스 접속:

| URL | 설명 |
|---|---|
| http://localhost:8000 | API |
| http://localhost:8000/docs | Swagger (`DEBUG=True` 시) |
| http://localhost:5555 | Flower — Celery 모니터링 |

---

## 환경변수

`.env.example`을 복사해 `.env`를 만들고 값을 채워주세요.

| 변수 | 설명 | 필수 |
|---|---|:---:|
| `DATABASE_URL` | PostgreSQL 비동기 URL (`postgresql+asyncpg://...`) | ✅ |
| `DATABASE_SYNC_URL` | PostgreSQL 동기 URL (`postgresql+psycopg2://...`) | ✅ |
| `REDIS_URL` | Redis URL | ✅ |
| `SECRET_KEY` | JWT 서명 키 | ✅ |
| `OPENAI_API_KEY` | OpenAI API 키 | ✅ |
| `STEAM_API_KEY` | Steam Web API 키 | |
| `MAIL_*` | Gmail SMTP 설정 | |
| `CELERY_BROKER_URL` | Celery 브로커 Redis URL | ✅ |
| `CELERY_RESULT_BACKEND` | Celery 결과 저장 Redis URL | ✅ |

> **Docker 환경**: DB/Redis 호스트를 컨테이너 이름으로 지정해야 합니다.
> `localhost` → `gembti_postgres` / `gembti_redis`

---

## Docker 세팅

### Dockerfile 구조 (멀티스테이지)

```
builder  →  uv로 .venv에 의존성 설치
runtime  →  .venv만 복사 + 소스 복사, 전용 유저(appuser)로 실행
```

### 컨테이너 구성 (로컬 / 개발 서버)

| 컨테이너 | 이미지 | 역할 |
|---|---|---|
| `gembti_app` | 프로젝트 빌드 | FastAPI (uvicorn) |
| `gembti_celery` | 프로젝트 빌드 | Celery Worker |
| `gembti_postgres` | pgvector/pgvector:pg16 | PostgreSQL + pgvector |
| `gembti_redis` | redis:7-alpine | Redis |
| `gembti_nginx` | nginx:alpine | 리버스 프록시 |

### 명령어



# 로컬 개발 모드 (핫리로드 + Flower)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# 로그
docker compose logs -f app

# 종료
docker compose down
```

---

## 데이터베이스 마이그레이션

```bash
# 마이그레이션 파일 생성
alembic revision --autogenerate -m "설명"

# 적용
alembic upgrade head

# 롤백
alembic downgrade -1

# Docker 환경
docker compose exec app alembic upgrade head
```

> 새 모델 추가 시 `alembic/env.py`의 모델 import 주석을 해제해야 자동 감지됩니다.

---

## 테스트

```bash
# 전체 테스트 + 커버리지
uv run pytest

# 특정 파일
uv run pytest tests/test_security.py -v

# HTML 커버리지 리포트
uv run pytest --cov=app --cov-report=html
```

현재 커버리지: **90%** (app/core 기준)

| Fixture | DB 필요 | 용도 |
|---|:---:|---|
| `anon_client` | ❌ | DB 없이 사용하는 기본 클라이언트 |
| `client` | ✅ | DB 세션이 주입된 클라이언트 |
| `db_session` | ✅ | DB 세션 직접 사용 |

---

