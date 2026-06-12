from __future__ import annotations

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.game.client import fetch_app_list
from app.game.repository import get_all_app_ids
from app.game.service import fetch_and_save_games

logger = logging.getLogger(__name__)

# EC2 micro 기준: 동시 HTTP 요청 2개, 배치 50개
_SEMAPHORE = 2
_BATCH_SIZE = 50


@celery_app.task(name="game.collect_games")
def collect_games_task(app_ids: list[int]) -> dict:
    """Steam API에서 게임 데이터를 수집해 DB에 저장하는 Celery 태스크.

    Args:
        app_ids: 수집할 Steam 앱 ID 목록

    Returns:
        {"success": int, "failed": int}
    """

    async def _run() -> dict:
        async with AsyncSessionLocal() as session:
            success, failed = await fetch_and_save_games(session, app_ids, concurrency=_SEMAPHORE)
        return {"success": success, "failed": failed}

    return asyncio.run(_run())


@celery_app.task(name="game.refresh_all_games", time_limit=21600)  # 최대 6시간
def refresh_all_games_task() -> dict:
    """매주 월요일 — Steam 전체 앱 목록에서 DB에 없는 새 게임만 추가한다.

    Returns:
        {"new_games": int, "success": int, "failed": int}
    """

    async def _run() -> dict:
        steam_ids, existing_ids = await asyncio.gather(
            fetch_app_list(),
            _get_existing_ids(),
        )
        new_ids = list(set(steam_ids) - existing_ids)
        total = len(new_ids)
        logger.info("신규 게임 추가 시작: %d개", total)

        success, failed = 0, 0
        for i in range(0, total, _BATCH_SIZE):
            batch = new_ids[i : i + _BATCH_SIZE]
            async with AsyncSessionLocal() as session:
                s, f = await fetch_and_save_games(session, batch, concurrency=_SEMAPHORE)
            success += s
            failed += f

        logger.info("신규 게임 추가 완료: 성공 %d / 실패 %d", success, failed)
        return {"new_games": total, "success": success, "failed": failed}

    async def _get_existing_ids() -> set[int]:
        async with AsyncSessionLocal() as session:
            return set(await get_all_app_ids(session))

    return asyncio.run(_run())
