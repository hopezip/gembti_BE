import pytest


def _analyze(query: str):
    try:
        from app.chat.rag.query import analyze_support_query
    except ModuleNotFoundError:
        pytest.fail("support query analyzer module is missing")
    return analyze_support_query(query)


def test_analyze_support_query_treats_steam_spacing_variant_as_support() -> None:
    analysis = _analyze("스팀연동")

    assert analysis.compact_text == "steam연동"
    assert analysis.support_intent == "likely_support"
    assert "steam" in analysis.category_hints
    assert "steam" in analysis.support_terms
    assert "연동" in analysis.support_terms
    assert analysis.off_topic_signals == ()


def test_analyze_support_query_keeps_programming_library_off_topic() -> None:
    analysis = _analyze("파이썬 라이브러리 추천해줘")

    assert analysis.support_intent == "likely_off_topic"
    assert "programming" in analysis.off_topic_signals


def test_analyze_support_query_recovers_bare_library_as_ambiguous_support() -> None:
    analysis = _analyze("라이브러리")

    assert analysis.support_intent == "ambiguous_support"
    assert "라이브러리" in analysis.support_terms
    assert "steam" in analysis.category_hints
    assert "recommendation" in analysis.category_hints


@pytest.mark.parametrize(
    ("query", "expected_category"),
    [
        ("회원가입", "account"),
        ("성향 스탯이 없다고 나와요", "recommendation"),
        ("내 취향에 맞는 게임 하나 바로 골라줘", "recommendation"),
        ("게임은 어디서 검색하나요?", "game"),
        ("친구랑 같이 할 게임만 보고 싶어요", "game"),
        ("세션", "account"),
    ],
)
def test_analyze_support_query_covers_eval_set_support_terms(
    query: str,
    expected_category: str,
) -> None:
    analysis = _analyze(query)

    assert analysis.support_intent != "likely_off_topic"
    assert expected_category in analysis.category_hints
