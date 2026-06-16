"""기존 게임의 is_active를 현재 성인 필터 로직으로 재평가한다.

성인 게임 필터(_is_adult_game)를 강화한 뒤, 이미 DB에 저장된 게임에 반영하기 위한
일회성 스크립트. Steam API를 호출하지 않고 steam_detail_json만으로 재판별한다.

사용 예시
---------
# 미리보기 (DB 변경 없이 비활성화 예정 게임만 출력)
python scripts/refilter_adult_games.py --dry-run

# 실제 반영
python scripts/refilter_adult_games.py

EC2 Docker 환경
--------------
docker exec gembti_app python scripts/refilter_adult_games.py --dry-run
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from sqlalchemy import select

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import app.core.model_registry as _model_registry  # noqa: E402, F401
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.game.models import Game  # noqa: E402
from app.game.service import _is_adult_game  # noqa: E402

_BATCH_SIZE = 200


async def _refilter(dry_run: bool) -> None:
    async with AsyncSessionLocal() as session:
        games = list((await session.execute(select(Game))).scalars().all())
        total = len(games)
        click.echo(f"대상 게임 {total:,}개")

        newly_blocked: list[str] = []
        for index, game in enumerate(games, start=1):
            should_be_active = not _is_adult_game(game.steam_detail_json or {})

            if game.is_active and not should_be_active:
                newly_blocked.append(game.title)

            if not dry_run and game.is_active != should_be_active:
                game.is_active = should_be_active

            if not dry_run and index % _BATCH_SIZE == 0:
                await session.commit()

        if dry_run:
            click.echo(f"[dry-run] 신규 차단 예정: {len(newly_blocked):,}개 (DB 미반영)")
            for title in newly_blocked[:30]:
                click.echo(f"  - {title}")
            if len(newly_blocked) > 30:
                click.echo(f"  ... 외 {len(newly_blocked) - 30:,}개")
            return

        await session.commit()
        click.echo(f"재평가 완료: 신규 차단 {len(newly_blocked):,}개")


@click.command()
@click.option("--dry-run", is_flag=True, default=False, help="DB 변경 없이 차단 예정만 출력")
def main(dry_run: bool) -> None:
    """기존 게임의 is_active를 현재 성인 필터로 재평가한다."""
    asyncio.run(_refilter(dry_run))


if __name__ == "__main__":
    main()
