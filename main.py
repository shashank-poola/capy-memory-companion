"""
Capy Example - Interactive Chat with Memory.

This example demonstrates how to use CapyMemory to build a chatbot that
remembers useful facts from conversations.
"""

from capy.core.openai import get_openai_client
from capy.core.settings import get_settings
from capy.db.database import SessionLocal, create_table
from capy.db.models.conversation import Conversation
from capy.db.models.profile import Profile
from capy.memory.memory import CapyMemory


PROFILE_NAME = "Shashank"
MEMORY_RETRIEVAL_LIMIT = 10
CHAT_HISTORY_LIMIT = 10


def build_chat_messages(
    user_message: str,
    memories_text: str,
    conversation_context: dict,
) -> list[dict[str, str]]:
    """Build Capy's bounded, evidence-aware response prompt."""
    summary_text = conversation_context.get("summary") or "No summary yet."
    recent_messages = conversation_context.get("messages") or []
    recent_text = "\n".join(
        f"{message['role'].upper()}: {message['content']}"
        for message in recent_messages
    ) or "No previous messages."

    return [
        {
            "role": "system",
            "content": (
                "You are Capy, a warm, grounded, thoughtful companion.\n"
                "Your stable character values patience, clarity, gentle humor, "
                "and honest uncertainty. Be kind and concise without sounding "
                "like a generic scripted assistant. Do not repeatedly introduce "
                "yourself or add a generic offer of help after every answer.\n\n"
                "Character and evidence rules:\n"
                "- Respond directly to the user's latest message.\n"
                "- Show empathy without claiming human experiences, private "
                "feelings, or memories that were not supplied.\n"
                "- Use recent conversation and active memories for continuity, "
                "but treat prior assistant messages as dialogue context, not "
                "proof of a user fact.\n"
                "- Distinguish current facts, historical facts, and plans. Do "
                "not describe a planned technology as currently used.\n"
                "- Never infer a technical cause, personal detail, or secret "
                "that the user did not explicitly provide. Say when something "
                "is unknown.\n\n"
                f"Conversation Summary:\n{summary_text}\n\n"
                f"Recent Conversation:\n{recent_text}\n\n"
                f"User Memories:\n{memories_text}"
            ),
        },
        {"role": "user", "content": user_message},
    ]


def chat_with_memory(
    user_message: str,
    memory: CapyMemory,
    conversation_id: int,
) -> str:
    """
    Generate a response using memories from the current profile.
    """
    settings = get_settings()
    client = get_openai_client()

    # Search for relevant memories.
    relevant_memories = memory.search(
        query=user_message,
        conversation_id=conversation_id,
        limit=MEMORY_RETRIEVAL_LIMIT,
    )

    # Format memories and bounded conversation context for the prompt.
    memories_text = "\n".join(
        f"- {item['memory']}" for item in relevant_memories["results"]
    ) or "No memories yet."
    conversation_context = memory.get_conversation_context(
        conversation_id,
        message_limit=CHAT_HISTORY_LIMIT,
    )
    messages = build_chat_messages(
        user_message=user_message,
        memories_text=memories_text,
        conversation_context=conversation_context,
    )

    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
    )

    assistant_message = (
        response.choices[0].message.content if response.choices else None
    )
    if not assistant_message:
        raise RuntimeError("The configured LLM returned an empty response.")

    # Store this conversation in memory.
    memory.add(
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ],
        conversation_id=conversation_id,
    )

    return assistant_message


def main() -> None:
    """
    Main entry point - interactive Capy chat loop.
    """
    print("=" * 50)
    print("Capy Chat Demo")
    print("=" * 50)
    print()

    # Step 1: Configure through environment variables or configure().
    # configure(general_compute_api_key="...")

    # Step 2: Create database tables.
    create_table()

    # Step 3: Create a session, profile, and memory instance.
    db = SessionLocal()

    try:
        profile = db.query(Profile).filter(Profile.name == PROFILE_NAME).first()
        if profile is None:
            profile = Profile(name=PROFILE_NAME)
            db.add(profile)
            db.commit()

        conversation_input = input(
            "Enter conversation ID (or press Enter for new): "
        ).strip()

        if conversation_input and conversation_input.isdigit():
            conversation_id = int(conversation_input)
            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.profile_id == profile.id,
                )
                .first()
            )

            if conversation:
                print(f"Resuming conversation: {conversation_id}")
            else:
                existing_conversation = db.get(Conversation, conversation_id)
                if existing_conversation:
                    raise ValueError(
                        f"Conversation {conversation_id} belongs to another profile."
                    )

                conversation = Conversation(
                    id=conversation_id,
                    profile_id=profile.id,
                )
                db.add(conversation)
                db.commit()
                print(f"Created new conversation: {conversation_id}")
        else:
            conversation = Conversation(profile_id=profile.id)
            db.add(conversation)
            db.commit()
            conversation_id = conversation.id
            print(f"Created new conversation: {conversation_id}")

        memory = CapyMemory(db)

        print()
        print("Chat started! Type 'exit' to quit, 'memories' to see stored memories.")
        print("-" * 50)

        # Chat loop.
        while True:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit"}:
                print("Goodbye!")
                break

            if user_input.lower() == "memories":
                # Show relevant active memories for this conversation.
                results = memory.search(
                    query="What do you remember about me?",
                    conversation_id=conversation_id,
                    limit=20,
                )
                print("\n--- Stored Capy Memories ---")
                for item in results["results"]:
                    print(f"  [{item['memory_id']}] {item['memory']}")
                if not results["results"]:
                    print("  No memories stored yet.")
                print("-" * 25)
                continue

            # Get and persist Capy's response.
            response = chat_with_memory(user_input, memory, conversation_id)
            print(f"\nCapy: {response}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
