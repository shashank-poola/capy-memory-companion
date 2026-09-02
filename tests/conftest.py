from collections.abc import Iterator
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from capy.core.openai import reset_client
from capy.core.settings import configure, get_settings, reset_settings
from capy.db.database import Base
from capy.db.models.conversation import Conversation
from capy.db.models.conversation_summary import ConversationSummary
from capy.db.models.memory import Memory
from capy.db.models.message import Message
from capy.db.models.profile import Profile
from capy.memory.vector_store import reset_vector_stores


@pytest.fixture(autouse=True)
def reset_capy_state() -> Iterator[None]:
    """Reset process-wide Capy state between tests."""
    reset_settings()
    reset_client()
    reset_vector_stores()
    yield
    reset_settings()
    reset_client()
    reset_vector_stores()


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Provide an isolated in-memory SQLite session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(
        autoflush=False,
        autocommit=False,
        bind=engine,
    )
    session = testing_session()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def offline_settings():
    """Configure providers for tests that must not call external services."""
    configure(
        general_compute_api_key="test-key",
        database_url="sqlite:///:memory:",
        embedding_provider="local",
    )
    return get_settings()


@pytest.fixture
def profile_conversation(db_session: Session) -> tuple[Profile, Conversation]:
    """Create one profile and one conversation for a test."""
    profile = Profile(name="Shashank")
    db_session.add(profile)
    db_session.commit()

    conversation = Conversation(profile_id=profile.id)
    db_session.add(conversation)
    db_session.commit()

    return profile, conversation


@pytest.fixture
def live_settings():
    """Enable live tests only when explicitly requested by the caller."""
    if os.environ.get("CAPY_RUN_LIVE_E2E") != "1":
        pytest.skip("Set CAPY_RUN_LIVE_E2E=1 to run credit-consuming live tests")

    settings = get_settings()
    if not settings.general_compute_api_key:
        pytest.fail("GENERAL_COMPUTE_API_KEY is required for live tests")
    if settings.llm_provider != "general_compute":
        pytest.fail("Live tests require LLM_PROVIDER=general_compute")

    return settings
