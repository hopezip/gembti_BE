from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.steam import tasks


class FakeRedis:
    def __init__(self, lock_acquired: bool = True) -> None:
        self.lock_acquired = lock_acquired
        self.deleted_keys: list[str] = []

    async def set(
        self,
        key: str,
        value: str,
        ex: int,
        nx: bool,
    ) -> bool:
        return self.lock_acquired

    async def delete(self, key: str) -> int:
        self.deleted_keys.append(key)
        return 1


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


def test_is_steam_library_sync_due_without_last_synced_at() -> None:
    assert tasks.is_steam_library_sync_due(None) is True


def test_is_steam_library_sync_due_after_cooldown() -> None:
    now = datetime(2026, 6, 16, tzinfo=UTC)

    assert (
        tasks.is_steam_library_sync_due(
            last_synced_at=now - timedelta(hours=24),
            now=now,
        )
        is True
    )


def test_is_steam_library_sync_not_due_within_cooldown() -> None:
    now = datetime(2026, 6, 16, tzinfo=UTC)

    assert (
        tasks.is_steam_library_sync_due(
            last_synced_at=now - timedelta(hours=23, minutes=59),
            now=now,
        )
        is False
    )


@pytest.mark.asyncio
async def test_enqueue_steam_library_sync_if_due_skips_recent_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_user_ids: list[int] = []

    def enqueue(user_id: int) -> str:
        called_user_ids.append(user_id)
        return "task-id"

    monkeypatch.setattr(tasks, "enqueue_steam_library_sync", enqueue)

    task_id = await tasks.enqueue_steam_library_sync_if_due(
        user_id=7,
        last_synced_at=datetime.now(UTC),
    )

    assert task_id is None
    assert called_user_ids == []


@pytest.mark.asyncio
async def test_enqueue_steam_library_sync_if_due_skips_running_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_user_ids: list[int] = []

    async def get_fake_redis(_purpose: object) -> FakeRedis:
        return FakeRedis(lock_acquired=False)

    def enqueue(user_id: int) -> str:
        called_user_ids.append(user_id)
        return "task-id"

    monkeypatch.setattr(tasks, "get_redis", get_fake_redis)
    monkeypatch.setattr(tasks, "enqueue_steam_library_sync", enqueue)

    task_id = await tasks.enqueue_steam_library_sync_if_due(
        user_id=7,
        last_synced_at=None,
    )

    assert task_id is None
    assert called_user_ids == []


@pytest.mark.asyncio
async def test_enqueue_steam_library_sync_if_due_enqueues_when_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_user_ids: list[int] = []

    async def get_fake_redis(_purpose: object) -> FakeRedis:
        return FakeRedis(lock_acquired=True)

    def enqueue(user_id: int) -> str:
        called_user_ids.append(user_id)
        return "task-id"

    monkeypatch.setattr(tasks, "get_redis", get_fake_redis)
    monkeypatch.setattr(tasks, "enqueue_steam_library_sync", enqueue)

    task_id = await tasks.enqueue_steam_library_sync_if_due(
        user_id=7,
        last_synced_at=None,
    )

    assert task_id == "task-id"
    assert called_user_ids == [7]
