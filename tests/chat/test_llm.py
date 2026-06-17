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

    assert roles == ["system", "user", "assistant", "user", "user"]
    assert messages[1]["content"] == "old question"
    assert messages[2]["content"] == "old answer"
    assert "password reset is available" in messages[3]["content"]
    assert messages[-1]["content"] == "new question"


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

    assert roles == ["system", "user", "user"]
    assert "steam sync is available" in messages[1]["content"]
    assert messages[-1]["content"] == "how do I sync steam?"
