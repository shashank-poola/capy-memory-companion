from types import SimpleNamespace

from capy.db.models.memory import Memory
from capy.memory.memory import CapyMemory
from capy.memory.tool_classifier import ToolDecision
from capy.memory.vector_store import FAISSVectorStore

import capy.memory.add.add_updation_phase as update_phase_module
import capy.memory.bubble_creator as bubble_module
import capy.memory.connection_finder as connection_module
import capy.memory.extractor as extractor_module
import capy.memory.memory as memory_module
import capy.memory.similar_memory_search as similar_memory_search_module
import capy.utils.summary_generator as summary_generator_module


def _patch_offline_pipeline(monkeypatch):
    """Keep the real database/memory flow while replacing network providers."""
    vector_store = FAISSVectorStore(dimension=2)
    get_store = lambda conversation_id: vector_store
    rebuild_store = lambda db, conversation_id: vector_store
    embed = lambda text: [1.0, 0.0]

    monkeypatch.setattr(memory_module, "embed_text", embed)
    monkeypatch.setattr(update_phase_module, "embed_text", embed)
    monkeypatch.setattr(bubble_module, "embed_text", embed)

    monkeypatch.setattr(memory_module, "get_vector_store", get_store)
    monkeypatch.setattr(memory_module, "rebuild_index_from_db", rebuild_store)
    monkeypatch.setattr(memory_module, "save_vector_store", lambda conversation_id: None)
    monkeypatch.setattr(update_phase_module, "get_vector_store", get_store)
    monkeypatch.setattr(update_phase_module, "save_vector_store", lambda conversation_id: None)
    monkeypatch.setattr(bubble_module, "get_vector_store", get_store)
    monkeypatch.setattr(bubble_module, "save_vector_store", lambda conversation_id: None)
    monkeypatch.setattr(connection_module, "get_vector_store", get_store)
    monkeypatch.setattr(similar_memory_search_module, "get_vector_store", get_store)
    monkeypatch.setattr(similar_memory_search_module, "rebuild_index_from_db", rebuild_store)

    extraction_json = (
        '{"semantic": ["User likes tea"], '
        '"bubbles": [{"text": "User is preparing tea today", "importance": 0.8}]}'
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=extraction_json),
                        )
                    ]
                )
            )
        )
    )
    monkeypatch.setattr(extractor_module, "get_llm_client", lambda: fake_client)
    monkeypatch.setattr(summary_generator_module, "get_llm_client", lambda: fake_client)
    monkeypatch.setattr(
        update_phase_module,
        "llm_tool_call",
        lambda candidate_fact, similar_memories: ToolDecision(
            action="ADD",
            memory_id=None,
            text=candidate_fact,
        ),
    )

    return vector_store


def test_memory_add_search_and_soft_delete(
    db_session,
    profile_conversation,
    offline_settings,
    monkeypatch,
):
    """The full offline memory pipeline stores, searches, connects, and deletes."""
    vector_store = _patch_offline_pipeline(monkeypatch)
    _, conversation = profile_conversation
    memory = CapyMemory(db_session)

    result = memory.add(
        messages=[
            {"role": "user", "content": "I like tea."},
            {"role": "assistant", "content": "I will remember that."},
        ],
        conversation_id=conversation.id,
    )

    stored_memories = db_session.query(Memory).order_by(Memory.id).all()
    semantic = next(item for item in stored_memories if not item.is_episodic)
    bubble = next(item for item in stored_memories if item.is_episodic)

    assert result == {
        "semantic": ["User likes tea"],
        "bubbles": ["User is preparing tea today"],
    }
    assert len(stored_memories) == 2
    assert all(item.profile_id == conversation.profile_id for item in stored_memories)
    assert bubble.memory_metadata["connections"]["bubble_ids"] == [semantic.id]

    search_results = memory.search(
        query="tea",
        conversation_id=conversation.id,
        limit=5,
    )
    result_ids = {item["memory_id"] for item in search_results["results"]}
    assert semantic.id in result_ids
    assert bubble.id in result_ids

    memory.delete(semantic.id)
    db_session.expire_all()
    assert db_session.get(Memory, semantic.id).is_active is False

    active_results = memory.search(
        query="tea",
        conversation_id=conversation.id,
        limit=5,
    )
    assert semantic.id not in {
        item["memory_id"] for item in active_results["results"]
    }
    assert vector_store.count == 1


def test_memory_search_rebuilds_incomplete_index(
    db_session,
    profile_conversation,
    offline_settings,
    monkeypatch,
):
    """Search rebuilds FAISS when active database memories are missing."""
    vector_store = _patch_offline_pipeline(monkeypatch)
    _, conversation = profile_conversation
    first_memory = Memory(
        profile_id=conversation.profile_id,
        conversation_id=conversation.id,
        memory_text="User uses Python",
        embedding=[1.0, 0.0],
    )
    second_memory = Memory(
        profile_id=conversation.profile_id,
        conversation_id=conversation.id,
        memory_text="User uses FastAPI",
        embedding=[1.0, 0.0],
    )
    db_session.add_all([first_memory, second_memory])
    db_session.commit()
    vector_store.add(first_memory.id, first_memory.embedding)

    rebuild_calls = []

    def rebuild(db, conversation_id):
        rebuild_calls.append(conversation_id)
        vector_store.add(second_memory.id, second_memory.embedding)
        return vector_store

    monkeypatch.setattr(memory_module, "rebuild_index_from_db", rebuild)

    results = CapyMemory(db_session).search(
        query="What technologies do I use?",
        conversation_id=conversation.id,
        limit=10,
    )

    result_ids = {item["memory_id"] for item in results["results"]}
    assert rebuild_calls == [conversation.id]
    assert {first_memory.id, second_memory.id} <= result_ids


def test_memory_update_reindexes_text(db_session, profile_conversation, offline_settings, monkeypatch):
    """Updating a memory changes its text and searchable vector."""
    vector_store = _patch_offline_pipeline(monkeypatch)
    _, conversation = profile_conversation
    memory_record = Memory(
        profile_id=conversation.profile_id,
        conversation_id=conversation.id,
        memory_text="User likes tea",
        embedding=[1.0, 0.0],
    )
    db_session.add(memory_record)
    db_session.commit()
    vector_store.add(memory_record.id, [1.0, 0.0])

    monkeypatch.setattr(memory_module, "embed_text", lambda text: [0.0, 1.0])
    manager = CapyMemory(db_session)
    updated = manager.update(memory_record.id, "User likes coffee")

    assert updated.memory_text == "User likes coffee"
    assert updated.embedding == [0.0, 1.0]
    search_results = manager.search(
        query="coffee",
        conversation_id=conversation.id,
        limit=1,
    )
    assert search_results["results"][0]["memory_id"] == memory_record.id


def test_memory_replace_deactivates_old_record(
    db_session,
    profile_conversation,
    offline_settings,
    monkeypatch,
):
    """Replacing a fact deactivates the old record and stores the new fact."""
    vector_store = _patch_offline_pipeline(monkeypatch)
    _, conversation = profile_conversation
    old_memory = Memory(
        profile_id=conversation.profile_id,
        conversation_id=conversation.id,
        memory_text="User likes tea",
        embedding=[1.0, 0.0],
    )
    db_session.add(old_memory)
    db_session.commit()
    vector_store.add(old_memory.id, [1.0, 0.0])

    monkeypatch.setattr(
        update_phase_module,
        "search_similar_memories",
        lambda **kwargs: [old_memory],
    )
    monkeypatch.setattr(
        update_phase_module,
        "llm_tool_call",
        lambda candidate_fact, similar_memories: ToolDecision(
            action="REPLACE",
            memory_id=old_memory.id,
            text="User likes coffee",
        ),
    )

    update_phase_module.update_phase(
        db=db_session,
        candidate_facts=["User likes coffee"],
        conversation_id=conversation.id,
    )
    db_session.expire_all()

    replacement = db_session.query(Memory).filter_by(
        conversation_id=conversation.id,
        memory_text="User likes coffee",
        is_active=True,
    ).one()
    assert db_session.get(Memory, old_memory.id).is_active is False
    assert replacement.profile_id == conversation.profile_id
    assert vector_store.count == 1
