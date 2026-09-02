from types import SimpleNamespace

import main


def test_main_chat_uses_memory_and_persists_messages(monkeypatch):
    """The entry point searches memory, calls the LLM, and stores the pair."""
    llm_request = {}
    search_calls = []
    context_calls = []
    stored_calls = []

    def search(**kwargs):
        search_calls.append(kwargs)
        return {"results": [{"memory": "User likes tea"}]}

    def get_conversation_context(*args, **kwargs):
        context_calls.append((args, kwargs))
        return {
            "summary": "Shashank likes tea and builds backend systems.",
            "messages": [
                {"role": "user", "content": "I like tea."},
                {"role": "assistant", "content": "I will remember that."},
            ],
        }

    fake_memory = SimpleNamespace(
        search=search,
        get_conversation_context=get_conversation_context,
        add=lambda **kwargs: stored_calls.append(kwargs),
    )

    def create(**kwargs):
        llm_request.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Hello Shashank."),
                )
            ]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(llm_model="gpt-oss-120b"),
    )
    monkeypatch.setattr(main, "get_openai_client", lambda: fake_client)

    response = main.chat_with_memory(
        user_message="How are you?",
        memory=fake_memory,
        conversation_id=7,
    )

    assert response == "Hello Shashank."
    assert search_calls == [
        {"query": "How are you?", "conversation_id": 7, "limit": 10}
    ]
    assert context_calls == [
        ((7,), {"message_limit": 10})
    ]
    assert llm_request["model"] == "gpt-oss-120b"
    system_prompt = llm_request["messages"][0]["content"]
    assert "User likes tea" in system_prompt
    assert "Shashank likes tea and builds backend systems." in system_prompt
    assert "USER: I like tea." in system_prompt
    assert "Your stable character values patience" in system_prompt
    assert stored_calls == [
        {
            "messages": [
                {"role": "user", "content": "How are you?"},
                {"role": "assistant", "content": "Hello Shashank."},
            ],
            "conversation_id": 7,
        }
    ]
