from app.chat.cs import prompt as support_prompt
from app.chat.infrastructure.llm import _build_chat_messages
from app.chat.rag.model import ChatChunkHit


def test_build_chat_messages_accepts_recent_turns_as_role_messages() -> None:
    chunk = ChatChunkHit(
        content="password reset is available from account settings",
        source="support.account#chunk-0001",
    )

    messages = _build_chat_messages(
        question="new question",
        chunks=(chunk,),
        recent_turns=[
            {
                "user": "old question",
                "assistant": "old answer",
            },
        ],
    )

    roles = [message["role"] for message in messages]

    assert roles == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "old question"
    assert messages[2]["content"] == "old answer"
    final_prompt = messages[-1]["content"]
    assert "[참고 문서]" in final_prompt
    assert "password reset is available" in final_prompt
    assert "[질문]" in final_prompt
    assert "new question" in final_prompt


def test_build_chat_messages_works_without_recent_turns() -> None:
    chunk = ChatChunkHit(
        content="steam sync is available from the settings",
        source="support.steam#chunk-0001",
    )

    messages = _build_chat_messages(
        question="how do I sync steam?",
        chunks=(chunk,),
    )

    roles = [message["role"] for message in messages]

    assert roles == ["system", "user"]
    assert "steam sync is available" in messages[-1]["content"]
    assert "[질문]" in messages[-1]["content"]
    assert "how do I sync steam?" in messages[-1]["content"]


def test_build_chat_messages_formats_prompt_template_with_reference_and_question() -> None:
    chunk = ChatChunkHit(
        content="password reset is available from account settings",
        source="support.account#chunk-0001",
    )

    messages = _build_chat_messages(
        question="how do I reset my password?",
        chunks=(chunk,),
    )

    prompt_message = messages[-1]["content"]

    assert hasattr(support_prompt, "SUPPORT_ANSWER_USER_PROMPT_TEMPLATE")
    prompt_template = support_prompt.SUPPORT_ANSWER_USER_PROMPT_TEMPLATE
    assert "[참고 문서]" in prompt_template
    assert "{retrieved_chunks}" in prompt_template
    assert "[질문]" in prompt_template
    assert "{user_query}" in prompt_template

    assert "[참고 문서]" in prompt_message
    assert "[참고 문서 1]" in prompt_message
    assert "support.account#chunk-0001" not in prompt_message
    assert "password reset is available" in prompt_message
    assert "[질문]" in prompt_message
    assert "how do I reset my password?" in prompt_message


def test_build_chat_messages_forbids_user_visible_source_labels() -> None:
    chunk = ChatChunkHit(
        content="steam sync is available from the settings",
        source="support.steam#chunk-0001",
    )

    messages = _build_chat_messages(
        question="how do I sync steam?",
        chunks=(chunk,),
    )

    combined_prompt = "\n".join(message["content"] for message in messages)

    assert "출처를 표시하세요" not in combined_prompt
    assert "출처를 `출처: support.account#chunk-0001`처럼" not in combined_prompt
    assert "답변 본문에는 참고 문서 출처" in combined_prompt
    assert "참고 문서 번호" in combined_prompt
    assert "support.steam#chunk-0001" not in combined_prompt


def test_build_chat_messages_sets_core_support_policy() -> None:
    chunk = ChatChunkHit(
        content="steam sync is available from the settings",
        source="support.steam#chunk-0001",
    )

    messages = _build_chat_messages(
        question="how do I sync steam?",
        chunks=(chunk,),
    )

    system_message = messages[0]["content"]

    assert system_message.startswith("당신은 GEMBTI 웹앱의 고객센터 전문 어시스턴트입니다.")
    assert "GEMBTI 웹앱의 고객센터 전문 어시스턴트" in system_message
    assert "추측하지" in system_message
    assert "개인화 게임 추천을 직접 생성" in system_message
    assert "민감정보를 요청하지" in system_message


def test_build_chat_messages_requires_conditional_narrowing_for_ambiguous_support_queries() -> None:
    chunk = ChatChunkHit(
        content=(
            "Steam 라이브러리 정보를 GEMBTI가 활용하려면 Steam에서 필요한 정보가 "
            "공개되어 있어야 합니다."
        ),
        source="support.steam#chunk-0001",
    )

    messages = _build_chat_messages(
        question="라이브러리",
        chunks=(chunk,),
    )

    combined_prompt = "\n".join(message["content"] for message in messages)

    assert "짧거나 다의적인 고객센터 질문" in combined_prompt
    assert "Steam 라이브러리를 말씀하시는 거라면" in combined_prompt
    assert "참고 문서가 제공된 경우" in combined_prompt
    assert "제공된 자료에서 답을 찾을 수 없습니다" in combined_prompt
    assert "이 문구로 시작하지 마세요" in combined_prompt


def test_build_chat_messages_requires_broad_failure_narrowing_when_chunks_exist() -> None:
    chunk = ChatChunkHit(
        content=(
            "“안 돼요”, “안 떠요”, “안 보여요”처럼 범위가 넓은 질문에는 화면 이름, "
            "눌렀던 버튼, 표시된 오류 문구를 함께 알려 달라고 안내할 수 있습니다."
        ),
        source="support.troubleshooting#chunk-0001",
    )

    messages = _build_chat_messages(
        question="안 떠요",
        chunks=(chunk,),
    )

    combined_prompt = "\n".join(message["content"] for message in messages)

    assert "안 떠요" in combined_prompt
    assert "화면 이름" in combined_prompt
    assert "눌렀던 버튼" in combined_prompt
    assert "표시된 오류 문구" in combined_prompt
    assert "조건부 안내" in combined_prompt
