from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.chat.rag.model import CHAT_CHUNK_EMBEDDING_DIMENSIONS
from app.core.database import Base


class ChatChunk(Base):
    """고객센터 RAG 검색에 사용하는 ``chat_chunk`` 테이블."""

    __tablename__ = "chat_chunk"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(CHAT_CHUNK_EMBEDDING_DIMENSIONS),
        nullable=True,
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
