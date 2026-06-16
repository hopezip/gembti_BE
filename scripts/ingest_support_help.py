"""고객센터 도움말 Markdown을 chat_chunk 벡터 테이블에 적재하는 스크립트.

사용 예시
---------
# 기본: OpenAI와 DB를 호출하지 않고 문서 파싱과 chunk 생성만 확인
uv run python scripts/ingest_support_help.py

# 실제 적재: OpenAI embedding을 만들고 chat_chunk 테이블에 저장
uv run python scripts/ingest_support_help.py --apply

Docker 컨테이너 안에서 실제 적재하는 경우
------------------------------------
python scripts/ingest_support_help.py --apply
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

import click

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.chat.rag.chunking import (  # noqa: E402
    chunk_support_help_document,
    load_support_help_documents,
)


def _preview_ingest(directory: Path) -> tuple[int, int]:
    documents = load_support_help_documents(directory)
    total_chunks = 0

    for document in documents:
        chunks = chunk_support_help_document(document)
        total_chunks += len(chunks)
        click.echo(
            f"- {document.metadata.doc_id}: "
            f"sections={len(document.sections)}, chunks={len(chunks)}"
        )

    document_count = len(documents)

    click.echo(
        f"✅ 고객센터 도움말 dry-run 완료: documents={document_count}, " f"chunks={total_chunks}"
    )
    return document_count, total_chunks


def _ensure_corpus_exists(document_count: int, chunk_count: int) -> None:
    if document_count == 0:
        raise click.ClickException("고객센터 도움말 문서가 없습니다.")
    if chunk_count == 0:
        raise click.ClickException("고객센터 도움말 청크가 없습니다.")


def _ensure_apply_environment() -> None:
    if os.getenv("OPENAI_API_KEY", "").strip():
        return

    raise click.ClickException("OPENAI_API_KEY가 필요합니다. .env 또는 환경 변수에 설정해 주세요.")


async def _run_ingest(directory: Path) -> None:
    import importlib

    from app.chat.infrastructure.embedding import OpenAIEmbeddingClient
    from app.chat.infrastructure.vector_store import AsyncPgvectorChatChunkVectorStore
    from app.chat.rag.model import SUPPORT_RAG_SETTINGS
    from app.chat.rag.service import ingest_support_help_documents
    from app.core.database import AsyncSessionLocal

    importlib.import_module("app.core.model_registry")

    async with AsyncSessionLocal() as db:
        result = await ingest_support_help_documents(
            embedding_client=OpenAIEmbeddingClient.from_env(),
            vector_store=AsyncPgvectorChatChunkVectorStore(
                db,
                score_threshold=SUPPORT_RAG_SETTINGS.score_threshold,
            ),
            directory=directory,
        )
        await db.commit()

    click.echo(
        f"✅ 고객센터 도움말 적재 완료: documents={result.document_count}, "
        f"chunks={result.chunk_count}"
    )


@click.command()
@click.option(
    "--directory",
    default="docs/help/support",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="고객센터 공개 도움말 Markdown 폴더",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="OpenAI와 DB를 호출하지 않고 문서 파싱과 청크 생성만 확인",
)
@click.option(
    "--apply",
    is_flag=True,
    help="OpenAI와 DB를 호출해 실제로 chat_chunk 테이블에 적재",
)
def main(directory: Path, dry_run: bool, apply: bool) -> None:
    """고객센터 공개 도움말 Markdown을 chat_chunk 벡터 테이블에 적재한다."""
    if dry_run and apply:
        raise click.ClickException("--dry-run과 --apply는 함께 사용할 수 없습니다.")

    document_count, chunk_count = _preview_ingest(directory)

    if not apply:
        if not dry_run:
            click.echo("실제 적재하려면 --apply 옵션을 붙여 실행하세요.")
        return

    _ensure_corpus_exists(document_count, chunk_count)
    _ensure_apply_environment()
    asyncio.run(_run_ingest(directory))


if __name__ == "__main__":
    main()
