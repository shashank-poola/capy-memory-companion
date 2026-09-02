from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from capy.db.database import Base


class Profile(Base):
    """
    profiles
    --------
    id (PK)
    name
    created_at
    updated_at
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    conversations = relationship(
        "Conversation",
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    memories = relationship("Memory", back_populates="profile")
