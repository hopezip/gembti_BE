from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "gembti",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.auth.tasks",
        # 태스크 모듈 경로 추가 예시:
        # "app.chat.tasks",
        # "app.recommend.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
