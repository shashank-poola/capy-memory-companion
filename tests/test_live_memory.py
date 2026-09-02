import pytest

from capy.db.models.memory import Memory
from capy.db.models.message import Message
from capy.memory.memory import CapyMemory
from capy.memory.vector_store import reset_vector_stores
from main import chat_with_memory

import capy.memory.vector_store as vector_store_module


@pytest.mark.live
def test_live_capy_chat_and_memory_flow(
    db_session,
    profile_conversation,
    live_settings,
    monkeypatch,
    tmp_path,
):
    """Run one real Capy response and persist the resulting memory."""
    monkeypatch.setattr(
        vector_store_module,
        "get_index_path",
        lambda conversation_id: str(tmp_path / f"conversation_{conversation_id}"),
    )
    reset_vector_stores()

    _, conversation = profile_conversation
    memory = CapyMemory(db_session)
    response = chat_with_memory(
        "Please remember this long-term fact: my name is Shashank and I prefer tea.",
        memory,
        conversation.id,
    )

    messages = (
        db_session.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id)
        .all()
    )
    active_memories = (
        db_session.query(Memory)
        .filter(
            Memory.conversation_id == conversation.id,
            Memory.is_active.is_(True),
        )
        .all()
    )

    assert response.strip()
    assert [message.role for message in messages] == ["user", "assistant"]
    assert active_memories
    assert any(
        "shashank" in item.memory_text.lower()
        or "tea" in item.memory_text.lower()
        for item in active_memories
    )
