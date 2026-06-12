"""Steam 게임 대량 수집 스크립트

EC2 Docker DB에 Steam 게임 데이터를 저장한다.
진행 상황을 체크포인트 파일로 저장해 중단 후 이어받기가 가능하다.

사용 예시
---------
# 1) 기본: Steam에서 앱 목록을 받아 1,000개 수집
python scripts/collect_games.py --limit 1000

# 2) 이어받기: 5,001번째 게임부터 1,000개
python scripts/collect_games.py --offset 5000 --limit 1000

# 3) 전체 수집 (느림, EC2에서 실행 권장)
python scripts/collect_games.py --limit 0 --concurrency 10

# 4) 미리 준비한 app_id 목록 파일로 수집
#    (app_ids.json: [730, 1245620, 413150, ...])
python scripts/collect_games.py --ids-file app_ids.json --limit 500

# 5) 체크포인트 파일에서 자동 이어받기
python scripts/collect_games.py --resume

EC2 Docker 환경
--------------
docker exec -it gembti_app python scripts/collect_games.py --limit 1000
또는 호스트에서:
DATABASE_URL=postgresql+asyncpg://gembti:gembti@localhost:5432/gembti \\
python scripts/collect_games.py --limit 1000
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import signal
import sys
import time

import click
from tqdm import tqdm

# 프로젝트 루트를 sys.path에 추가
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.core.database import AsyncSessionLocal  # noqa: E402
import app.core.model_registry as _model_registry  # 모든 ORM 모델 등록 (relationship 해결용)  # noqa: E402, F401
from app.game.client import fetch_app_list  # noqa: E402
from app.game.repository import get_all_app_ids  # noqa: E402
from app.game.service import fetch_and_save_games  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,  # tqdm과 겹치지 않도록 WARNING으로 설정
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("collect_games")

CHECKPOINT_FILE = Path("/tmp/.collect_checkpoint.json")

# ── 인터럽트 처리 ──────────────────────────────────────────────────────────────

_interrupted = False


def _handle_sigint(sig, frame):  # noqa: ANN001
    global _interrupted
    _interrupted = True
    click.echo("\n\n⚠️  Ctrl+C 감지 — 현재 배치 완료 후 중단합니다...")


signal.signal(signal.SIGINT, _handle_sigint)


# ── 체크포인트 ─────────────────────────────────────────────────────────────────


def _load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_checkpoint(data: dict) -> None:
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2))


def _clear_checkpoint() -> None:
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


# ── 앱 목록 로드 ────────────────────────────────────────────────────────────────


async def _load_app_ids(ids_file: str | None) -> list[int]:
    """수집 대상 app_id 목록을 가져온다."""
    if ids_file:
        path = Path(ids_file)
        if not path.exists():
            click.echo(f"❌ 파일 없음: {ids_file}", err=True)
            sys.exit(1)
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [int(x) for x in data]
        # {"app_ids": [...]} 형식도 허용
        return [int(x) for x in data.get("app_ids", [])]

    click.echo("📋 Steam 앱 목록 조회 중...", err=True)
    ids = await fetch_app_list()
    if not ids:
        click.echo(
            "❌ Steam GetAppList API 실패.\n"
            "   EC2가 아닌 로컬에서 실행 중이라면 Steam IP 제한일 수 있습니다.\n"
            "   --ids-file 옵션으로 미리 받아놓은 app_id 파일을 지정하세요.",
            err=True,
        )
        sys.exit(1)
    ids.sort(reverse=True)
    click.echo(f"   → {len(ids):,}개 앱 조회 완료 (최신순)", err=True)
    return ids


async def _get_existing_ids() -> set[int]:
    async with AsyncSessionLocal() as session:
        return set(await get_all_app_ids(session))


# ── 핵심 수집 루프 ─────────────────────────────────────────────────────────────


async def _collect(
    app_ids: list[int],
    concurrency: int,
    batch_size: int,
    start_idx: int,
    checkpoint_data: dict,
) -> tuple[int, int, int]:
    """
    Returns:
        (total_success, total_failed, last_processed_idx)
    """
    total_success = checkpoint_data.get("success", 0)
    total_failed = checkpoint_data.get("failed", 0)
    last_idx = start_idx

    remaining = app_ids[start_idx:]
    total = len(remaining)

    if total == 0:
        return total_success, total_failed, last_idx

    pbar = tqdm(
        total=total,
        desc="수집",
        unit="게임",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    )

    for batch_start in range(0, total, batch_size):
        if _interrupted:
            break

        batch = remaining[batch_start : batch_start + batch_size]
        batch_idx = start_idx + batch_start

        async with AsyncSessionLocal() as session:
            success, failed = await fetch_and_save_games(session, batch, concurrency=concurrency)

        total_success += success
        total_failed += failed
        last_idx = batch_idx + len(batch)

        pbar.update(len(batch))
        pbar.set_postfix(
            성공=total_success,
            실패=total_failed,
            현재=last_idx,
        )

        # 체크포인트 저장
        _save_checkpoint(
            {
                "last_idx": last_idx,
                "success": total_success,
                "failed": total_failed,
                "timestamp": datetime.now().isoformat(),
                "total_app_ids": len(app_ids),
            }
        )

    pbar.close()
    return total_success, total_failed, last_idx


# ── CLI 진입점 ─────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--limit",
    "-n",
    default=1000,
    type=int,
    show_default=True,
    help="수집할 최대 게임 수 (0 = 전체)",
)
@click.option(
    "--offset",
    default=0,
    type=int,
    show_default=True,
    help="앱 목록의 시작 인덱스 (이어받기용)",
)
@click.option(
    "--concurrency",
    "-c",
    default=5,
    type=int,
    show_default=True,
    help="동시 HTTP 요청 수",
)
@click.option(
    "--batch-size",
    "-b",
    default=100,
    type=int,
    show_default=True,
    help="한 번에 DB에 커밋하는 게임 수",
)
@click.option(
    "--ids-file",
    default=None,
    type=str,
    help="app_id 목록 JSON 파일 경로 (없으면 Steam API 자동 조회)",
)
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    show_default=True,
    help="이미 DB에 있는 게임 건너뛰기",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="마지막 체크포인트에서 이어받기",
)
@click.option(
    "--save-ids",
    default=None,
    type=str,
    help="Steam 앱 목록을 파일로 저장 후 종료 (예: app_ids.json)",
)
def main(
    limit: int,
    offset: int,
    concurrency: int,
    batch_size: int,
    ids_file: str | None,
    skip_existing: bool,
    resume: bool,
    save_ids: str | None,
) -> None:
    """Steam 게임 데이터를 DB에 대량 수집한다."""

    # ── 체크포인트 이어받기 ────────────────────────────────────────────────
    checkpoint_data: dict = {}
    if resume:
        cp = _load_checkpoint()
        if cp:
            offset = cp["last_idx"]
            checkpoint_data = cp
            click.echo(
                f"📌 체크포인트 발견: {cp['last_idx']:,}번째부터 이어받기\n"
                f"   이전 성공: {cp['success']:,}개 / 실패: {cp['failed']:,}개"
            )
        else:
            click.echo("ℹ️  체크포인트 없음 — 처음부터 시작합니다.")

    asyncio.run(
        _main_async(
            limit=limit,
            offset=offset,
            concurrency=concurrency,
            batch_size=batch_size,
            ids_file=ids_file,
            skip_existing=skip_existing,
            checkpoint_data=checkpoint_data,
            save_ids=save_ids,
        )
    )


async def _main_async(
    limit: int,
    offset: int,
    concurrency: int,
    batch_size: int,
    ids_file: str | None,
    skip_existing: bool,
    checkpoint_data: dict,
    save_ids: str | None,
) -> None:
    t_start = time.monotonic()

    # ── 앱 목록 로드 ──────────────────────────────────────────────────────
    all_ids = await _load_app_ids(ids_file)

    # --save-ids 옵션: 목록만 저장하고 종료
    if save_ids:
        Path(save_ids).write_text(json.dumps(all_ids, indent=2))
        click.echo(f"✅ {len(all_ids):,}개 app_id를 {save_ids}에 저장했습니다.")
        return

    # ── 이미 수집된 게임 제외 ──────────────────────────────────────────────
    if skip_existing:
        click.echo("🔍 DB에서 기존 app_id 조회 중...", err=True)
        existing = await _get_existing_ids()
        before = len(all_ids)
        all_ids = [x for x in all_ids if x not in existing]
        click.echo(
            f"   → 기존 {len(existing):,}개 제외 → 수집 대상 {len(all_ids):,}개 "
            f"(전체 {before:,}개 중)",
            err=True,
        )

    # ── offset + limit 적용 ───────────────────────────────────────────────
    if offset:
        all_ids = all_ids[offset:]

    if limit and limit > 0:
        all_ids = all_ids[:limit]

    click.echo(
        f"\n🚀 수집 시작\n"
        f"   대상: {len(all_ids):,}개 | 동시요청: {concurrency} | 배치: {batch_size}\n"
        f"   예상 시간: ~{len(all_ids) / concurrency * 0.6 / 60:.0f}분 (이론치)\n"
    )

    if not all_ids:
        click.echo("✅ 수집할 게임이 없습니다.")
        return

    # ── 수집 실행 ─────────────────────────────────────────────────────────
    success, failed, last_idx = await _collect(
        app_ids=all_ids,
        concurrency=concurrency,
        batch_size=batch_size,
        start_idx=0,
        checkpoint_data=checkpoint_data,
    )

    elapsed = time.monotonic() - t_start

    # ── 결과 출력 ─────────────────────────────────────────────────────────
    click.echo(
        f"\n{'─' * 50}\n"
        f"  ✅ 성공: {success:,}개\n"
        f"  ❌ 실패: {failed:,}개  (type≠game, API 오류 등)\n"
        f"  ⏱  소요: {elapsed:.0f}초 ({elapsed / 60:.1f}분)\n"
        f"{'─' * 50}"
    )

    if _interrupted:
        click.echo(
            f"\n⚠️  중단됨 (처리: {last_idx:,}/{len(all_ids):,})\n"
            f"   이어받기: python scripts/collect_games.py --resume\n"
        )
    else:
        _clear_checkpoint()
        click.echo("✅ 수집 완료 — 체크포인트 파일 삭제됨\n")


if __name__ == "__main__":
    main()
