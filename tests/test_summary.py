from types import SimpleNamespace

from capy.db.models.conversation_summary import ConversationSummary
from capy.db.models.message import Message
from capy.utils import summary_generator


def _fake_summary_client(responses, calls):
    def create(**kwargs):
        calls.append(kwargs)
        content = responses.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                )
            ]
        )

    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )


def test_summary_is_created_and_updated_at_trigger(db_session, profile_conversation, monkeypatch, offline_settings):
    """A summary is created at 20 messages and updated without duplicates."""
    _, conversation = profile_conversation
    db_session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"message {index}",
            )
            for index in range(20)
        ]
    )
    db_session.commit()

    calls = []
    fake_client = _fake_summary_client(
        [
            "The user is testing Capy memory.",
            "The user is continuing to test Capy memory.",
        ],
        calls,
    )
    monkeypatch.setattr(summary_generator, "get_llm_client", lambda: fake_client)

    first_summary = summary_generator.generate_conversation_summary(
        db_session,
        conversation.id,
    )
    second_summary = summary_generator.generate_conversation_summary(
        db_session,
        conversation.id,
    )

    stored_summaries = db_session.query(ConversationSummary).filter_by(
        conversation_id=conversation.id
    ).all()
    assert first_summary == "The user is testing Capy memory."
    assert second_summary == "The user is continuing to test Capy memory."
    assert len(stored_summaries) == 1
    assert stored_summaries[0].summary_text == second_summary
    assert len(calls) == 2
    assert "message 0" in calls[0]["messages"][1]["content"]
