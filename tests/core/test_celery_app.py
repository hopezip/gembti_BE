from app.core.celery_app import celery_app


def test_withdrawal_cleanup_is_not_registered_in_beat_schedule() -> None:
    schedule = celery_app.conf.beat_schedule

    assert "cleanup-withdrawn-users-every-day" not in schedule
    assert "app.auth.tasks" not in celery_app.conf.include
