from app.core.celery_app import celery_app


def test_cleanup_withdrawn_users_is_registered_in_beat_schedule() -> None:
    schedule = celery_app.conf.beat_schedule

    cleanup_schedule = schedule["cleanup-withdrawn-users-every-day"]

    assert cleanup_schedule["task"] == "app.auth.tasks.cleanup_withdrawn_users"
