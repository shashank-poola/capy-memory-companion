from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON as JSONType
from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from capy.db.database import Base


class Memory(Base):
    """
    memories
    ----------------------
    id (PK)
    profile_id (FK -> profiles.id)
    conversation_id (FK -> conversations.id)
    memory_text     (the memory fact)
    category        (optional: "preference", "profile", "hobby", etc.)
    embedding       (vector)
    memory_metadata (JSON: timestamps, tags, source message IDs)
    created_at
    updated_at
    """

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    memory_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    embedding: Mapped[List[float]] = mapped_column(JSONType, nullable=True)
    memory_metadata: Mapped[Optional[Dict]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"),
    )

    # New additions
    is_episodic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    occurred_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # Relationships
    profile = relationship("Profile", back_populates="memories")
    conversation = relationship("Conversation", back_populates="memories")
