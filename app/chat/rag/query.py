"""고객센터 RAG용 질의 분석.

이 모듈은 긴급 임시 lexical recovery를 위한 작은 규칙 계층이다. 진짜
hybrid-search RAG 아키텍처 전환이 아니라, 기존 dense pgvector 검색 앞뒤에
붙는 보강 장치로 유지한다.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal
import unicodedata

SupportIntent = Literal["likely_support", "ambiguous_support", "likely_off_topic"]

_SUPPORT_TERM_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], bool], ...] = (
    ("steam", ("steam",), ("steam",), False),
    ("스팀연동", ("steam", "연동"), ("steam",), False),
    ("steam연동", ("steam", "연동"), ("steam",), False),
    ("연동", ("연동",), ("steam",), False),
    ("연결", ("연결",), ("steam", "account"), True),
    ("라이브러리", ("라이브러리",), ("steam", "recommendation"), True),
    ("공개", ("공개",), ("steam",), True),
    ("동기화", ("동기화",), ("steam", "troubleshooting"), True),
    ("비밀번호", ("비밀번호",), ("account", "troubleshooting"), False),
    ("인증번호", ("인증번호",), ("account", "troubleshooting"), False),
    ("인증", ("인증",), ("account", "troubleshooting"), True),
    ("회원가입", ("회원가입",), ("account",), False),
    ("로그인", ("로그인",), ("account", "troubleshooting"), False),
    ("로그아웃", ("로그아웃",), ("account",), False),
    ("탈퇴", ("탈퇴",), ("account",), False),
    ("닉네임", ("닉네임",), ("account",), False),
    ("세션", ("세션",), ("account", "troubleshooting"), True),
    ("내정보", ("내정보", "정보"), ("account",), False),
    ("내 정보", ("내정보", "정보"), ("account",), False),
    ("설문", ("설문",), ("survey",), False),
    ("성향스탯", ("성향", "스탯"), ("recommendation", "survey"), False),
    ("성향 스탯", ("성향", "스탯"), ("recommendation", "survey"), False),
    ("스탯", ("스탯",), ("recommendation", "survey"), False),
    ("취향", ("취향",), ("recommendation", "survey"), True),
    ("결과", ("결과",), ("survey", "recommendation"), True),
    ("추천기록", ("추천", "기록"), ("recommendation",), False),
    ("추천 기록", ("추천", "기록"), ("recommendation",), False),
    ("추천", ("추천",), ("recommendation",), False),
    ("검색", ("검색",), ("game", "troubleshooting"), False),
    ("친구랑", ("친구랑",), ("game",), False),
    ("가격", ("가격",), ("game", "recommendation"), True),
    ("평점", ("평점",), ("game", "recommendation"), True),
    ("세일", ("세일",), ("game", "recommendation"), False),
    ("인기", ("인기",), ("game", "recommendation"), False),
    ("장르", ("장르",), ("game",), False),
    ("사양", ("사양",), ("game",), False),
    ("게임검색", ("게임", "검색"), ("game",), False),
    ("게임 검색", ("게임", "검색"), ("game",), False),
    ("안돼", ("안돼",), ("troubleshooting", "general"), True),
    ("안되", ("안되",), ("troubleshooting", "general"), True),
    ("안떠", ("안떠",), ("troubleshooting", "general"), True),
    ("안 떠", ("안떠",), ("troubleshooting", "general"), True),
    ("안보여", ("안보여",), ("troubleshooting", "general"), True),
    ("안 보여", ("안보여",), ("troubleshooting", "general"), True),
    ("오류", ("오류",), ("troubleshooting", "general"), True),
)

_NEGATIVE_SIGNAL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "programming",
        (
            "python",
            "파이썬",
            "javascript",
            "자바스크립트",
            "react",
            "상태관리",
            "설치법",
            "코딩",
            "프로그래밍",
        ),
    ),
    ("finance", ("주식", "환율")),
    ("weather", ("날씨",)),
    ("steam_platform", ("환불 정책", "steam guard", "steamguard", "스팀덱")),
    ("live_data", ("실시간", "동접자", "지금 제일 높은", "제일 높은", "할인율")),
    ("internal", ("시스템 프롬프트", "gpt", "모델 이름")),
    ("secret", ("api 키", "apikey", "토큰", "비밀번호 맞혀", "비밀번호 맞춰")),
    ("medical", ("의학 상담", "의료 상담")),
    ("legal", ("법률 자문", "법률 상담")),
    ("general_writing", ("이력서",)),
    ("shopping", ("맥북",)),
    ("health", ("다이어트", "식단")),
    ("travel", ("여행 일정",)),
    ("entertainment", ("영화 추천",)),
    ("education", ("수학 문제",)),
)


@dataclass(frozen=True)
class SupportQueryAnalysis:
    raw_text: str
    normalized_text: str
    compact_text: str
    support_terms: tuple[str, ...]
    category_hints: tuple[str, ...]
    off_topic_signals: tuple[str, ...]
    support_intent: SupportIntent

    @property
    def allows_lexical_recovery(self) -> bool:
        return self.support_intent != "likely_off_topic" and bool(self.support_terms)


def analyze_support_query(query: str) -> SupportQueryAnalysis:
    """사용자 query를 고객센터 검색 전용 신호로 정규화한다."""

    raw_text = query.strip()
    normalized_text = normalize_support_text(raw_text)
    compact_text = compact_support_text(raw_text)

    support_terms: list[str] = []
    category_hints: list[str] = []
    has_ambiguous_support_term = False
    for phrase, terms, categories, is_ambiguous in _SUPPORT_TERM_RULES:
        if _contains_phrase(normalized_text, compact_text, phrase):
            support_terms.extend(terms)
            category_hints.extend(categories)
            has_ambiguous_support_term = has_ambiguous_support_term or is_ambiguous

    off_topic_signals = [
        signal
        for signal, phrases in _NEGATIVE_SIGNAL_RULES
        if any(_contains_phrase(normalized_text, compact_text, phrase) for phrase in phrases)
    ]

    unique_support_terms = _dedupe(support_terms)
    unique_category_hints = _dedupe(category_hints)
    unique_off_topic_signals = _dedupe(off_topic_signals)
    if unique_off_topic_signals:
        support_intent: SupportIntent = "likely_off_topic"
    elif unique_support_terms and has_ambiguous_support_term:
        support_intent = "ambiguous_support"
    elif unique_support_terms:
        support_intent = "likely_support"
    else:
        support_intent = "ambiguous_support"

    return SupportQueryAnalysis(
        raw_text=raw_text,
        normalized_text=normalized_text,
        compact_text=compact_text,
        support_terms=unique_support_terms,
        category_hints=unique_category_hints,
        off_topic_signals=unique_off_topic_signals,
        support_intent=support_intent,
    )


def normalize_support_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("스팀", "steam")
    normalized = re.sub(r"[^\w가-힣]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def compact_support_text(text: str) -> str:
    return normalize_support_text(text).replace(" ", "")


def _contains_phrase(normalized_text: str, compact_text: str, phrase: str) -> bool:
    normalized_phrase = normalize_support_text(phrase)
    compact_phrase = compact_support_text(phrase)
    return normalized_phrase in normalized_text or compact_phrase in compact_text


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__ = [
    "SupportIntent",
    "SupportQueryAnalysis",
    "analyze_support_query",
    "compact_support_text",
    "normalize_support_text",
]
