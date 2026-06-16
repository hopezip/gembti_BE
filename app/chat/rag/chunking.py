"""고객센터 공개 도움말 Markdown을 ``chat_chunk`` 초안으로 변환한다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.chat.rag.model import (
    SUPPORT_RAG_SETTINGS,
    ChatChunkDraft,
    MetadataValidationError,
    SupportHelpChunk,
    SupportHelpDocument,
    SupportHelpMetadata,
    format_chat_chunk_source,
)

REQUIRED_FRONTMATTER_FIELDS = (
    "doc_id",
    "title",
    "category",
    "status",
    "visibility",
    "updated_at",
    "reviewed_at",
)


def parse_support_help_markdown(
    markdown: str,
    source_path: Path,
) -> SupportHelpDocument:
    """YAML-like frontmatter와 본문을 ``SupportHelpDocument``로 파싱한다."""

    metadata_text, body = _split_frontmatter(markdown, source_path)
    raw_metadata = _parse_simple_frontmatter(metadata_text, source_path)
    metadata = _build_support_help_metadata(raw_metadata, source_path)
    sections = _extract_h2_sections(body)
    return SupportHelpDocument(
        metadata=metadata,
        body=body.strip(),
        source_path=str(source_path),
        sections=sections,
    )


def chunk_support_help_document(
    document: SupportHelpDocument,
    *,
    chunk_size: int = SUPPORT_RAG_SETTINGS.chunk_size,
    chunk_overlap: int = SUPPORT_RAG_SETTINGS.chunk_overlap,
) -> list[SupportHelpChunk]:
    """문서 섹션을 RAG 검색용 청크 목록으로 나눈다."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    chunks: list[SupportHelpChunk] = []
    chunk_index = 1
    section_items = document.sections.items() or ((document.metadata.title, document.body),)
    for section, section_content in section_items:
        for content in _split_text(section_content, chunk_size, chunk_overlap):
            chunks.append(
                SupportHelpChunk(
                    doc_id=document.metadata.doc_id,
                    title=document.metadata.title,
                    category=document.metadata.category,
                    source_path=document.source_path,
                    section=section,
                    content=content,
                    source=format_chat_chunk_source(document.metadata.doc_id, chunk_index),
                )
            )
            chunk_index += 1
    return chunks


def chat_chunk_drafts_from_chunks(chunks: list[SupportHelpChunk]) -> list[ChatChunkDraft]:
    """임베딩 전 청크를 ``chat_chunk`` DB 저장 초안으로 변환한다."""

    return [chunk.to_chat_chunk_draft() for chunk in chunks]


def load_support_help_documents(
    directory: Path | str = Path("docs/help/support"),
) -> list[SupportHelpDocument]:
    """고객센터 공개 도움말 Markdown 파일들을 SupportHelpDocument 리스트로 로드한다."""

    support_dir = Path(directory)
    if not support_dir.exists():
        return []

    documents: list[SupportHelpDocument] = []
    for markdown_path in sorted(support_dir.glob("*.md")):
        markdown = markdown_path.read_text(encoding="utf-8")
        documents.append(
            parse_support_help_markdown(
                markdown,
                markdown_path,
            )
        )
    return documents


def _split_frontmatter(markdown: str, source_path: Path) -> tuple[str, str]:
    lines = markdown.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise MetadataValidationError(str(source_path), ["frontmatter must start with ---"])

    end_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if end_index is None:
        raise MetadataValidationError(str(source_path), ["frontmatter must end with ---"])

    metadata_text = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :])
    return metadata_text.strip(), body.strip()


def _parse_simple_frontmatter(
    metadata_text: str,
    source_path: Path,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in metadata_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            if current_list_key is None:
                raise MetadataValidationError(
                    str(source_path),
                    [f"list item without key: {line}"],
                )
            metadata.setdefault(current_list_key, []).append(line[2:].strip())
            continue

        if ":" not in line:
            raise MetadataValidationError(str(source_path), [f"invalid metadata line: {line}"])
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key:
            raise MetadataValidationError(str(source_path), ["metadata key must not be blank"])
        if value:
            metadata[key] = value
            current_list_key = None
        else:
            metadata[key] = []
            current_list_key = key

    return metadata


def _build_support_help_metadata(
    raw_metadata: dict[str, Any],
    source_path: Path,
) -> SupportHelpMetadata:
    problems = [
        f"{field_name} is required"
        for field_name in REQUIRED_FRONTMATTER_FIELDS
        if not str(raw_metadata.get(field_name, "")).strip()
    ]
    raw_tags = raw_metadata.get("tags", [])
    if raw_tags is None:
        raw_tags = []
    if not isinstance(raw_tags, list):
        problems.append("tags must be a list")
        raw_tags = []
    if problems:
        raise MetadataValidationError(str(source_path), problems)

    return SupportHelpMetadata(
        doc_id=str(raw_metadata["doc_id"]).strip(),
        title=str(raw_metadata["title"]).strip(),
        category=str(raw_metadata["category"]).strip(),
        status=str(raw_metadata["status"]).strip(),
        visibility=str(raw_metadata["visibility"]).strip(),
        tags=tuple(str(tag).strip() for tag in raw_tags if str(tag).strip()),
        updated_at=str(raw_metadata["updated_at"]).strip(),
        reviewed_at=str(raw_metadata["reviewed_at"]).strip(),
    )


def _extract_h2_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_title: str | None = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_title = line.removeprefix("## ").strip()
            sections.setdefault(current_title, [])
            continue
        if current_title is None:
            continue
        sections[current_title].append(line)

    return {
        title: _normalize_section_text(lines)
        for title, lines in sections.items()
        if _normalize_section_text(lines)
    }


def _normalize_section_text(lines: list[str]) -> str:
    return "\n".join(line.strip() for line in lines).strip()


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [" ".join(words)]

    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step
    return chunks


__all__ = [
    "chat_chunk_drafts_from_chunks",
    "chunk_support_help_document",
    "load_support_help_documents",
    "parse_support_help_markdown",
]
