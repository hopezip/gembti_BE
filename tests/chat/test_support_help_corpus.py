from pathlib import Path

from app.chat.rag.chunking import chunk_support_help_document, load_support_help_documents


def test_general_support_help_first_chunk_contains_service_intro_keywords() -> None:
    documents = load_support_help_documents(Path("docs/help/support"))
    general = next(
        document for document in documents if document.metadata.doc_id == "support.general"
    )

    first_chunk = chunk_support_help_document(general)[0]

    assert first_chunk.source == "support.general#chunk-0001"
    assert "GEMBTI" in first_chunk.content
    assert "서비스" in first_chunk.content
    assert "사이트" in first_chunk.content
