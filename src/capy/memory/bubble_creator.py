"""
Bubble Creator - Creates episodic memory bubbles.
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from capy.db.models.conversation import Conversation
from capy.db.models.memory import Memory
from capy.memory.embeddings import embed_text
from capy.memory.connection_finder import find_connections
from capy.memory.vector_store import get_vector_store, save_vector_store


def create_bubbles(
    db: Session,
    bubbles: List[Dict],
    conversation_id: int,
    session_id: Optional[int] = None
) -> List[Memory]:
    """
    Create bubble memories and find their connections.

    Args:
        bubbles: [{"text": "...", "importance": 0.7}, ...]

    Returns:
        List of created Memory objects
    """
    created = []
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation with ID {conversation_id} not found")

    profile_id = conversation.profile_id
    vector_store = get_vector_store(conversation_id)

    for bubble_data in bubbles:
        text = bubble_data.get("text", "")
        importance = bubble_data.get("importance", 0.5)

        if not text:
            continue

        # Ensure importance is a float
        if isinstance(importance, str):
            try:
                importance = float(importance)
            except ValueError:
                importance = 0.5

        # Generate embedding
        embedding = embed_text(text)

        # Create bubble record
        bubble = Memory(
            profile_id=profile_id,
            conversation_id=conversation_id,
            memory_text=text,
            embedding=embedding,
            is_episodic=True,
            occurred_at=datetime.now(timezone.utc),
            session_id=session_id,
            importance=importance,
            is_active=True,
            memory_metadata={}
        )

        db.add(bubble)
        db.flush()  # Get ID before finding connections

        # Add to FAISS index
        vector_store.add(bubble.id, embedding)

        # Find connections (imported from connection_finder.py)
        find_connections(db, bubble, conversation_id)

        created.append(bubble)

    # Save FAISS index
    save_vector_store(conversation_id)

    db.commit()
    return created