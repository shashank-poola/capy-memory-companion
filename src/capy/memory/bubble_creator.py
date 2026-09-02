"""
Bubble Creator - Creates episodic memory bubbles.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from capy.db.models.conversation import Conversation
from capy.db.models.memory import Memory
from capy.memory.embeddings import embed_text
from capy.memory.connection_finder import find_connections
from capy.memory.similarity import cosine_similarity
from capy.memory.vector_store import get_vector_store, save_vector_store


BUBBLE_DUPLICATE_THRESHOLD = 0.92
BUBBLE_DEDUPLICATION_WINDOW = timedelta(days=7)


def _normalise_text(text: str) -> str:
    """Normalize text for exact bubble duplicate detection."""
    return " ".join(re.findall(r"\\w+", text.casefold()))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _find_recent_duplicate(
    db: Session,
    conversation_id: int,
    text: str,
    embedding: List[float],
    now: datetime,
) -> Memory | None:
    """Find a very similar active bubble from the recent conversation window."""
    normalized_text = _normalise_text(text)
    cutoff = now - BUBBLE_DEDUPLICATION_WINDOW
    candidates = db.query(Memory).filter(
        Memory.conversation_id == conversation_id,
        Memory.is_episodic.is_(True),
        Memory.is_active.is_(True),
    ).all()

    for candidate in candidates:
        if candidate.occurred_at and _as_utc(candidate.occurred_at) < cutoff:
            continue
        if normalized_text == _normalise_text(candidate.memory_text):
            return candidate
        if candidate.embedding and cosine_similarity(embedding, candidate.embedding) >= BUBBLE_DUPLICATE_THRESHOLD:
            return candidate
    return None


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

        # Generate embedding and consolidate a very recent near-duplicate.
        embedding = embed_text(text)
        now = datetime.now(timezone.utc)
        duplicate = _find_recent_duplicate(
            db=db,
            conversation_id=conversation_id,
            text=text,
            embedding=embedding,
            now=now,
        )
        if duplicate:
            # Keep the more descriptive wording while refreshing recency.
            text_to_store = (
                text if len(text) > len(duplicate.memory_text) else duplicate.memory_text
            )
            if text_to_store != duplicate.memory_text:
                duplicate_embedding = embed_text(text_to_store)
                vector_store.remove(duplicate.id)
                duplicate.memory_text = text_to_store
                duplicate.embedding = duplicate_embedding
                vector_store.add(duplicate.id, duplicate_embedding)
            duplicate.occurred_at = now
            duplicate.updated_at = now
            duplicate.importance = max(duplicate.importance or 0.0, float(importance))
            find_connections(db, duplicate, conversation_id)
            created.append(duplicate)
            continue

        # Create bubble record
        bubble = Memory(
            profile_id=profile_id,
            conversation_id=conversation_id,
            memory_text=text,
            embedding=embedding,
            is_episodic=True,
            occurred_at=now,
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