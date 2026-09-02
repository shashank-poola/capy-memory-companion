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
        limit=10,
    )

    # Format memories for the prompt.
    memories_text = "\n".join(
        f"- {item['memory']}" for item in relevant_memories["results"]
    ) or "No memories yet."

    # Generate a response with memory context.
    messages = [
        {
            "role": "system",
            "content": (
                "You are Capy, a warm, thoughtful, patient, and honest companion.\n"
                "Be concise, kind, and helpful. Use the user's memories to "
                "personalize your responses when relevant, but do not mention "
                "internal memory systems unless the user asks. Never claim to "
                "remember anything that is not present in the conversation or "
                "supplied memory context. Treat the user with patience and "
                "respect.\n\n"
                f"User Memories:\n{memories_text}"
            ),
        },
        {"role": "user", "content": user_message},
    ]

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
