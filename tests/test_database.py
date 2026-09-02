from sqlalchemy import inspect

from capy.db.models.conversation_summary import ConversationSummary
from capy.db.models.memory import Memory


def test_compact_memory_schema_is_registered(db_session):
    """The database exposes the requested compact memory schema."""
    tables = set(inspect(db_session.bind).get_table_names())
    assert {
        "profiles",
        "conversations",
        "conversation_summary",
        "memories",
        "messages",
    } <= tables

    columns = {
        column["name"]
        for column in inspect(db_session.bind).get_columns("memories")
    }
    assert columns == {
        "id",
        "profile_id",
        "conversation_id",
        "memory_text",
        "category",
        "embedding",
        "memory_metadata",
        "created_at",
        "updated_at",
        "is_episodic",
        "occurred_at",
        "session_id",
        "importance",
        "is_active",
    }


def test_profile_memory_and_summary_persist(db_session, profile_conversation):
    """Profiles, memories, and conversation summaries persist together."""
    profile, conversation = profile_conversation
    memory = Memory(
        profile_id=profile.id,
        conversation_id=conversation.id,
        memory_text="User likes tea",
        embedding=[1.0, 0.0],
        memory_metadata={"source": "test"},
    )
    summary = ConversationSummary(
        conversation_id=conversation.id,
        summary_text="The user likes tea.",
    )
    db_session.add_all([memory, summary])
    db_session.commit()
    db_session.refresh(memory)
    db_session.refresh(summary)

    assert memory.profile_id == profile.id
    assert memory.conversation_id == conversation.id
    assert memory.memory_text == "User likes tea"
    assert memory.memory_metadata == {"source": "test"}
    assert memory.is_episodic is False
    assert memory.importance == 0.5
    assert memory.is_active is True
    assert summary.summary_text == "The user likes tea."
    assert conversation.profile_id == profile.id
