from types import SimpleNamespace

import pytest

from app.steam import tasks


def test_enqueue_steam_library_sync_calls_celery_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_user_ids: list[int] = []

    def delay(user_id: int) -> SimpleNamespace:
        called_user_ids.append(user_id)
        return SimpleNamespace(id="task-id")

    monkeypatch.setattr(tasks.sync_steam_library_task, "delay", delay)

    task_id = tasks.enqueue_steam_library_sync(7)

    assert task_id == "task-id"
    assert called_user_ids == [7]
