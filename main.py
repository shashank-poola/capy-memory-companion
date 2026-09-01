"""Interactive Capy chat entry point backed by the local database."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from capy.core.openai import get_llm_client
from capy.core.settings import get_settings
from capy.db.database import SessionLocal, create_table
from capy.db.models.conversation import Conversation
from capy.db.models.memory import Memory
from capy.db.models.message import Message
from capy.db.models.profile import Profile

CAPY_SYSTEM_PROMPT = """You are Capy, a warm and thoughtful companion.
Be concise, honest, and helpful. Do not claim to remember information unless it
is present in the conversation context. Treat the user with patience and respect."""


def get_or_create_profile(session: Session, name: str) -> Profile:
    """Return the named profile used to keep the local conversation persistent."""
    profile = session.query(Profile).filter(Profile.name == name).first()
    if profile is None:
        profile = Profile(name=name)
        session.add(profile)
        session.commit()
    return profile


def get_or_create_conversation(session: Session, profile: Profile) -> Conversation:
    """Return the most recently used conversation for the profile."""
    conversation = (
        session.query(Conversation)
        .filter(Conversation.profile_id == profile.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .first()
    )
    if conversation is None:
        conversation = Conversation(profile_id=profile.id)
        session.add(conversation)
        session.commit()
    return conversation


def build_messages(conversation: Conversation, user_message: str) -> list[dict[str, str]]:
    """Build a short provider request from Capy's persona and recent messages."""
    recent_messages: Iterable[Message] = conversation.messages[-8:]
    messages = [{"role": "system", "content": CAPY_SYSTEM_PROMPT}]
    messages.extend(
        {"role": message.role, "content": message.content} for message in recent_messages
    )
    messages.append({"role": "user", "content": user_message})
    return messages


def chat_with_capy(session: Session, conversation: Conversation, user_message: str) -> str:
    """Generate and persist one Capy response."""
    settings = get_settings()
    client = get_llm_client()
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=build_messages(conversation, user_message),
    )
    assistant_message = response.choices[0].message.content if response.choices else None
    if not assistant_message:
        raise RuntimeError("General Compute returned an empty response.")

    user_record = Message(
        conversation_id=conversation.id,
        role="user",
        content=user_message,
    )
    assistant_record = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_message,
    )
    session.add_all([user_record, assistant_record])
    session.commit()
    return assistant_message


def show_memories(session: Session, profile: Profile) -> None:
    """Print currently active profile memories without exposing inactive history."""
    memories = (
        session.query(Memory)
        .filter(Memory.profile_id == profile.id, Memory.is_active.is_(True))
        .order_by(Memory.updated_at.desc())
        .all()
    )
    print("\n--- Active Capy memories ---")
    if not memories:
        print("  No active memories stored yet.")
    for memory in memories:
        print(f"  [{memory.id}] {memory.memory_text}")
    print("-" * 28)


def main() -> None:
    """Run the interactive Capy chat loop."""
    print("=" * 50)
    print("Capy Chat")
    print("=" * 50)
    print("Type 'exit' to quit or 'memories' to list active memories.")

    create_table()
    session = SessionLocal()
    try:
        profile = get_or_create_profile(session, "default")
        conversation = get_or_create_conversation(session, profile)
        while True:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                break
            if user_input.lower() == "memories":
                show_memories(session, profile)
                continue
            print(f"\nCapy: {chat_with_capy(session, conversation, user_input)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
