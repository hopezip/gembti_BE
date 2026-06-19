from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "gembti",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.game.tasks",
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
    beat_schedule={
        "refresh-games-every-monday": {
            "task": "game.refresh_all_games",
            "schedule": crontab(hour=3, minute=0, day_of_week=1),  # 매주 월요일 03:00 KST
        },
        "refresh-existing-games-every-day": {
            "task": "game.refresh_existing_games",
            "schedule": crontab(hour=5, minute=0),  # 매일 05:00 KST
        },
    },
)
