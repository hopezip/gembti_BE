from pathlib import Path

from sqlalchemy import Text

from app.support.models import SupportHelpDocChunk, SupportHelpDocument

MIGRATION_PATH = Path("alembic/versions/2026-06-01_13-45-59_create_support_help_rag_tables.py")


def test_support_help_models_are_rag_only():
    assert SupportHelpDocument.__tablename__ == "support_help_documents"
    assert SupportHelpDocChunk.__tablename__ == "support_help_doc_chunks"
    model_text = Path("app/support/models.py").read_text(encoding="utf-8")
    assert "support_chat_sessions" not in model_text
    assert "support_chat_messages" not in model_text


def test_support_help_document_model_matches_live_table_contract():
    columns = SupportHelpDocument.__table__.c

    assert list(columns.keys()) == [
        "id",
        "source_path",
        "title",
        "doc_category",
        "evidence_status",
        "source_url",
        "is_active",
        "created_at",
        "updated_at",
    ]
    assert columns.source_path.type.length == 500
    assert columns.source_path.unique is True
    assert columns.title.type.length == 300
    assert set(columns.doc_category.type.enums) == {
        "account",
        "steam",
        "survey",
        "result",
        "community",
        "limits",
        "general",
    }
    assert "general" in str(columns.doc_category.server_default.arg)
    assert set(columns.evidence_status.type.enums) == {
        "reviewed",
        "generated",
        "deprecated",
    }
    assert "reviewed" in str(columns.evidence_status.server_default.arg)
    assert columns.source_url.nullable is True
    assert columns.source_url.type.length == 500
    assert columns.is_active.nullable is False
    assert "true" in str(columns.is_active.server_default.arg).lower()


def test_support_help_doc_chunk_model_matches_live_table_contract():
    columns = SupportHelpDocChunk.__table__.c

    assert list(columns.keys()) == [
        "id",
        "support_help_document_id",
        "chunk_index",
        "section_title",
        "chunk_text",
        "keywords",
        "content_hash",
        "embedding_model",
        "vector_namespace",
        "embedding_vector",
        "is_active",
        "created_at",
        "updated_at",
    ]
    assert columns.section_title.nullable is True
    assert columns.section_title.type.length == 300
    assert isinstance(columns.chunk_text.type, Text)
    assert columns.chunk_text.nullable is False
    assert columns.keywords.nullable is True
    assert "[]" in str(columns.keywords.server_default.arg)
    assert columns.content_hash.type.length == 64
    assert columns.embedding_model.type.length == 100
    assert "text-embedding-3-small" in str(columns.embedding_model.server_default.arg)
    assert columns.vector_namespace.type.length == 100
    assert "support_help" in str(columns.vector_namespace.server_default.arg)
    assert columns.embedding_vector.nullable is False
    assert columns.is_active.nullable is False
    assert "true" in str(columns.is_active.server_default.arg).lower()


def test_support_help_migration_contains_required_vector_storage():
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "support_help_documents" in migration
    assert "support_help_doc_chunks" in migration
    assert "Vector(1536)" in migration
    assert "support_help" in migration
    assert "text-embedding-3-small" in migration
    assert "support_chat_sessions" not in migration
    assert "support_chat_messages" not in migration


def test_support_help_migration_matches_live_table_field_names():
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    for field_name in [
        "doc_category",
        "evidence_status",
        "source_url",
        "is_active",
        "section_title",
        "chunk_text",
    ]:
        assert field_name in migration

    assert 'sa.Column("status"' not in migration
    assert 'sa.Column("metadata"' not in migration
    assert 'sa.Column("section"' not in migration
    assert 'sa.Column("content"' not in migration
