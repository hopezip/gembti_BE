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
    assert "support.account#chunk-0001" in prompt_message
    assert "password reset is available" in prompt_message
    assert "[질문]" in prompt_message
    assert "how do I reset my password?" in prompt_message


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
