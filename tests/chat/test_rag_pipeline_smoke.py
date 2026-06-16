# =============================================================================
# [모듈 개요] tests/chat/test_rag_pipeline_smoke.py
#
# 책임: 고객센터 RAG 파이프라인(문서 파싱 → 청킹 → 임베딩 → 벡터 검색 → 응답)이
#       Fake 구현체로 끝까지 연결되는지 **스모크(연기) 테스트**로 검증한다.
#
# 개념:
#   - 스모크 테스트: 각 단계를 깊게 검증하기보다 "한 바퀴 돌아서 기대 출력이 나오는지"
#     빠르게 확인하는 통합 테스트. 세부 회귀는 tests/chat/test_rag_model.py 등에 위임.
#   - Fake* 클라이언트: OpenAI·DB·Redis 없이 CI에서 결정론적으로 동작하는 테스트 더블.
#   - async generator 소비: stream_answer()는 SSE처럼 str 조각을 yield → 테스트는 모아 문자열화.
#
# 파이프라인 위치 (이 파일이 검증하는 흐름):
#   MOCK_SUPPORT_HELP_MARKDOWN (인라인 fixture 문자열)
#       → app/chat/rag/chunking.py :: parse_support_help_markdown
#       → chunk_support_help_document → chat_chunk_drafts_from_chunks
#       → app/chat/infrastructure/embedding.py :: FakeEmbeddingClient.embed_text
#       → app/chat/infrastructure/vector_store.py :: ChatChunkVectorWrite / FakeChatChunkVectorStore
#       → app/chat/infrastructure/llm.py :: DeterministicSupportResponder.stream_answer
#       → assert (문서 메타·청크·검색·답변 문자열)
#
# 운영 / 테스트:
#   - network-free: FakeEmbeddingClient + FakeChatChunkVectorStore + DeterministicSupportResponder
#   - pytest-asyncio asyncio_mode=auto (pyproject.toml) → async def test_* 그대로 실행
#   - DB·HTTP·OpenAI 미사용 — conftest DB fixture도 이 파일 테스트에 불필요
#
# 다른 선택지:
#   - 단계별 unit test만 → 모듈 간 타입·필드명 불일치를 놓치기 쉬움
#   - 실 DB + OpenAI e2e → 느리고 API 키·플레이크·비용
#   - FastAPI TestClient로 /chat/cs 엔드포인트 → 라우터·DI까지 포함(더 무거움)
#   - Celery ingest 태스크까지 → 배치 경로 검증용, 답변 경로 스모크와 목적 다름
#
# 이 구현을 택한 근거:
#   - RAG 4계층(chunking / embedding / vector_store / llm) **배선** 한 번에 확인
#   - test_rag_model.py(모델·source 정규화)와 역할 분리 — 여기는 "파이프라인 연결"
#   - DeterministicSupportResponder로 LLM 없이도 stream_answer async 경로 검증
#
# 가장 기본적인 코드인가?
#   아니오. 더 단순히는 chunking 함수만 assert하는 unit test가 가능하지만,
#   embed → upsert → search → responder까지 이어지는 **통합 스모크**가 없으면
#   ChatChunkVectorWrite 필드·RetrievalResult.chunk 추출·tuple(list) 변환 등
#   경계에서 깨져도 CI가 통과할 수 있다.
# =============================================================================

from pathlib import Path  # source_path 인자용 — 실제 파일 I/O 없이 경로 문자열만 전달

from app.chat.infrastructure.embedding import (
    CHAT_CHUNK_EMBEDDING_DIMENSIONS,  # 1536 등 — entries/search 차원 assert에 사용
)
from app.chat.infrastructure.embedding import (
    FakeEmbeddingClient,  # 임베딩 Fake + 차원 상수; BLAKE2b 결정론 벡터 — OpenAI 호출 없음
)
from app.chat.infrastructure.llm import (
    DeterministicSupportResponder,  # 응답기 Fake + fallback 상수; "지원 문서 기준으로는 ..." 고정 포맷 — network-free
)
from app.chat.infrastructure.llm import (  # chunks 비었을 때 기대 문자열 — llm.py 단일 출처
    FALLBACK_ANSWER,
)
from app.chat.infrastructure.vector_store import (
    ChatChunkVectorWrite,  # upsert 페이로드 dataclass — DB id 붙이기 전 형태
)
from app.chat.infrastructure.vector_store import (
    FakeChatChunkVectorStore,  # 벡터 저장·검색 Fake; 인메모리 코사인 유사도 검색
)
from app.chat.rag.chunking import (
    chat_chunk_drafts_from_chunks,  # SupportHelpChunk → ChatChunkDraft(content, source)
)
from app.chat.rag.chunking import (
    chunk_support_help_document,  # SupportHelpDocument → 섹션별 SupportHelpChunk[]
)
from app.chat.rag.chunking import (
    parse_support_help_markdown,  # 마크다운 → 청크 파이프라인 (순수 함수); YAML frontmatter + 본문 → SupportHelpDocument
)

# =============================================================================
# MOCK_SUPPORT_HELP_MARKDOWN — 테스트 전용 최소 지원 문서
#
# 역할: docs/help/support/*.md 형식을 흉내 낸 **인라인 fixture** (디스크 파일 불필요).
# 입력: 없음 (모듈 로드 시 상수로 고정).
# 출력 / 사용처: parse_support_help_markdown(..., Path(...)) 의 markdown 인자.
#
# 남에게 설명할 포인트:
#   - frontmatter doc_id=support.account → chunk source가 support.account#chunk-0001 로 이어짐.
#   - "## Login" 한 섹션만 → len(chunks)==1 assert 근거.
#   - 본문 문장이 최종 answer에 substring으로 포함되는지 검증하는 텍스트.
# =============================================================================
MOCK_SUPPORT_HELP_MARKDOWN = """---
doc_id: support.account
title: Account help
category: account
status: reviewed
visibility: public
tags:
- account
- login
updated_at: 2026-06-11
reviewed_at: 2026-06-11
---
# Account help

## Login
Password reset is available from the account settings page.
"""


# =============================================================================
# _collect_answer — async stream_answer를 동기 테스트에서 소비하는 헬퍼
#
# 역할: DeterministicSupportResponder.stream_answer() async generator를 끝까지 읽어
#       하나의 str로 합친다 (프로덕션 SSE 클라이언트가 delta를 이어 붙이는 것과 동일).
# 입력:
#   - question: 사용자 질문 — responder.answer()에 전달(Deterministic은 del question으로 무시).
#   - chunks: list | tuple — SupportResponder Protocol과 동일; 빈 list면 FALLBACK_ANSWER.
# 출력 / 사용처: 두 test_* 함수의 answer 변수 ← assert 대상.
#
# 왜 `_` 접두사? Python 관례 — 이 모듈 내부 테스트 헬퍼, 외부 import 대상 아님.
# =============================================================================
async def _collect_answer(
    question: str, chunks
) -> str:  # chunks: list[ChatChunkHit] | tuple — 타입 힌트 생략(테스트 간결)
    responder = (
        DeterministicSupportResponder()
    )  # 매 호출 새 인스턴스 — 상태 없어서 재사용 가능하나 명시적
    deltas: list[str] = []  # stream에서 받은 토큰 조각 누적
    async for delta in responder.stream_answer(question, chunks):  # AsyncIterator[str] 소비
        deltas.append(delta)  # iter_text_deltas()가 쪼갠 조각 — 순서 유지 중요
    return "".join(deltas)  # 전체 답변 문자열 — assert in / == FALLBACK_ANSWER 에 사용


# =============================================================================
# test_mock_support_document_flows_through_rag_pipeline — RAG 전 구간 스모크
#
# 역할: mock 마크다운 한 건이 parse → chunk → embed → upsert → search → answer 까지
#       끊김 없이 흐르는지 단계별 중간 산출물과 최종 답을 assert.
# 입력: MOCK_SUPPORT_HELP_MARKDOWN + 고정 질문 "How do I reset my password?"
# 출력: pytest assert 통과/실패 — 실패 시 어느 계층에서 배선이 끊겼는지 역추적 가능.
# =============================================================================
async def test_mock_support_document_flows_through_rag_pipeline() -> (
    None
):  # asyncio_mode=auto → await 없이 async def만으로 실행
    # --- 1) 문서 파싱: frontmatter 검증 + 섹션 추출 ---
    document = parse_support_help_markdown(  # str + Path → SupportHelpDocument
        MOCK_SUPPORT_HELP_MARKDOWN,  # 인라인 fixture 본문
        Path(
            "docs/help/support/account.md"
        ),  # 가짜 경로 — validate_metadata·로그용; 파일 읽기 없음
    )
    chunks = chunk_support_help_document(
        document
    )  # SupportHelpChunk[] — 섹션당 1청크(여기선 Login 1개)
    drafts = chat_chunk_drafts_from_chunks(
        chunks
    )  # ChatChunkDraft[] — DB chat_chunk 행의 content/source만

    # --- 2) 임베딩 + 벡터 저장 (ingest 측면 미니 재현) ---
    embedder = FakeEmbeddingClient()  # 기본 dimensions=CHAT_CHUNK_EMBEDDING_DIMENSIONS
    vector_store = FakeChatChunkVectorStore()  # 인메모리; score_threshold 기본 0.0
    entries = [  # list comprehension — draft마다 ChatChunkVectorWrite 한 행
        ChatChunkVectorWrite(
            content=draft.content,  # 청크 본문 — __post_init__에서 strip 검증
            source=draft.source,  # 예: support.account#chunk-0001 — parse_chat_chunk_source 검증
            embedding_vector=tuple(
                embedder.embed_text(draft.content)
            ),  # list→tuple: frozen dataclass·DB 호환
        )
        for draft in drafts  # drafts 순회 — 여기서는 1건
    ]

    vector_store.upsert(entries)  # Fake 저장소에 적재 — 이후 search 대상
    query_embedding = embedder.embed_text("How do I reset my password?")  # 사용자 질문 벡터화
    results = vector_store.search(  # 코사인 유사도 top_k — RetrievalResult[] 반환
        query_embedding,
        top_k=3,  # 최대 3건 — fixture는 1청크뿐이라 results 길이 1 기대
        category_hint="account",  # doc category와 매칭 힌트 — Fake 구현에서 필터·부스트에 사용될 수 있음
    )
    answer = await _collect_answer(  # 검색 hit의 chunk만 responder에 전달 (프로덕션 cs/service와 동일 형태)
        "How do I reset my password?",  # 질문 문자열 — Deterministic은 내용 무시, 시그니처 호환용
        [result.chunk for result in results],  # list[ChatChunkHit] — Protocol union 중 list 쪽
    )

    # --- 3) 단계별 회귀 assert — 스모크이지만 중간 산출물도 고정해 디버깅 용이 ---
    assert document.metadata.doc_id == "support.account"  # frontmatter doc_id 파싱
    assert document.sections == {  # ## Login 아래 본문만 dict 값으로
        "Login": "Password reset is available from the account settings page."
    }
    assert len(chunks) == 1  # 섹션 1개 → SupportHelpChunk 1개
    assert drafts[0].source == "support.account#chunk-0001"  # format_chat_chunk_source 규칙
    assert len(entries[0].embedding_vector) == CHAT_CHUNK_EMBEDDING_DIMENSIONS  # embed 차원 일치
    assert len(results) == 1  # 저장 1건 + query 유사 → hit 1건
    assert results[0].chunk.source == "support.account#chunk-0001"  # 검색 결과 source 보존
    assert (
        "Password reset is available from the account settings page." in answer
    )  # RAG 근거가 답에 반영
    assert answer != FALLBACK_ANSWER  # chunks 있을 때 fallback 아님 — 검색·응답 경로 정상


# =============================================================================
# test_support_responder_returns_fallback_when_no_chunks_are_retrieved — 빈 검색 방어
#
# 역할: vector search가 0건일 때(또는 responder에 빈 chunks) FALLBACK_ANSWER만 반환하는지 확인.
#       test_mock_* 가 "happy path"면 이 테스트는 **검색 실패 / 근거 없음** 분기.
# 입력: 동일 질문 + chunks=[] — upsert/search 단계 생략(응답기만 격리해도 되지만 E2E 관점에서 helper 재사용).
# 출력: answer == FALLBACK_ANSWER — llm.py DeterministicSupportResponder.answer() early return과 일치.
# =============================================================================
async def test_support_responder_returns_fallback_when_no_chunks_are_retrieved() -> None:
    answer = await _collect_answer(
        "How do I reset my password?", []
    )  # 빈 list — Protocol에서 len()==0

    assert (
        answer == FALLBACK_ANSWER
    )  # "지원 문서에서 답을 찾지 못했습니다"류 고정 문구 — OpenAI 미호출
