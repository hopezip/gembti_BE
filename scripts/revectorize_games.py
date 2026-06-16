"""기존 게임의 trait_vector를 현재 매핑 로직으로 재계산한다.

매핑 알고리즘(대비 지수, 장르 순서 가중치)을 바꾼 뒤 이미 DB에 저장된
게임들의 trait_vector에 반영하기 위한 일회성 스크립트.
Steam API를 호출하지 않고 steam_detail_json만으로 재벡터화하므로 빠르다.

game.genres 컬럼은 현지화된 한글 이름이라 매핑 테이블(영문 키)과 맞지 않으므로,
원래 수집 로직과 동일하게 steam_detail_json의 장르 ID에서 영문명을 다시 도출한다.

사용 예시
---------
# 미리보기 (DB 변경 없이 변화량만 출력)
python scripts/revectorize_games.py --dry-run

# 실제 재벡터화
python scripts/revectorize_games.py

EC2 Docker 환경
--------------
docker exec gembti_app python scripts/revectorize_games.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import click
from sqlalchemy import select

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.core.database import AsyncSessionLocal  # noqa: E402
import app.core.model_registry as _model_registry  # noqa: E402, F401
from app.core.recommendation.vectorizer import game_to_vector  # noqa: E402
from app.game.models import Game  # noqa: E402
from app.game.service import _CATEGORY_ID_EN, _GENRE_ID_EN  # noqa: E402

_BATCH_SIZE = 200


def _english_traits(detail_json: dict) -> tuple[list[str], list[str]]:
    """steam_detail_json의 장르/카테고리 ID를 매핑 테이블 키(영문)로 변환한다."""
    genres_raw = detail_json.get("genres") or []
    categories_raw = detail_json.get("categories") or []
    genres = [_GENRE_ID_EN.get(str(g.get("id", "")), g.get("description", "")) for g in genres_raw]
    categories = [
        _CATEGORY_ID_EN.get(str(c.get("id", "")), c.get("description", "")) for c in categories_raw
    ]
    return genres, categories


async def _revectorize(dry_run: bool) -> None:
    async with AsyncSessionLocal() as session:
        games = list((await session.execute(select(Game))).scalars().all())
        total = len(games)
        click.echo(f"대상 게임 {total:,}개")

        changed = 0
        for index, game in enumerate(games, start=1):
            genres, categories = _english_traits(game.steam_detail_json or {})
            new_vector = game_to_vector(genres, categories)
            old_vector = [float(v) for v in game.trait_vector]

            if any(abs(a - b) > 1e-6 for a, b in zip(new_vector, old_vector, strict=True)):
                changed += 1
                if not dry_run:
                    game.trait_vector = new_vector

            if not dry_run and index % _BATCH_SIZE == 0:
                await session.commit()
                click.echo(f"  {index:,}/{total:,} 커밋")

        if dry_run:
            click.echo(f"[dry-run] 변경 예정: {changed:,}/{total:,}개 (DB 미반영)")
            return

        await session.commit()
        click.echo(f"재벡터화 완료: {changed:,}/{total:,}개 갱신")


@click.command()
@click.option("--dry-run", is_flag=True, default=False, help="DB 변경 없이 변화량만 출력")
def main(dry_run: bool) -> None:
    """기존 게임의 trait_vector를 현재 매핑 로직으로 재계산한다."""
    asyncio.run(_revectorize(dry_run))


if __name__ == "__main__":
    main()
