"""
Centralized settings module for Capy.

Supports two configuration methods:
1. Programmatic: configure(general_compute_api_key="...", database_url="...")
2. Environment variables: GENERAL_COMPUTE_API_KEY, DATABASE_URL

Supports the configured chat providers:
- general_compute: General Compute's OpenAI-compatible API
- openrouter: OpenRouter's OpenAI-compatible API

Embeddings default to a local model so retrieval does not require API credits.
"""

import os
from dataclasses import dataclass
from typing import Literal, Optional

from dotenv import load_dotenv

LLMProvider = Literal["general_compute", "openrouter"]
EmbeddingProvider = Literal["local", "openrouter"]

GENERAL_COMPUTE_BASE_URL = "https://api.generalcompute.com/v1"
LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class CapySettings:
    """Configuration settings for Capy."""

    general_compute_api_key: Optional[str] = None
    database_url: Optional[str] = None
    debug: bool = False

    # LLM provider settings
    llm_provider: LLMProvider = "general_compute"
    general_compute_base_url: str = GENERAL_COMPUTE_BASE_URL
    openrouter_api_key: Optional[str] = None
    llm_model: str = "gpt-oss-120b"

    # Embedding provider settings
    embedding_provider: EmbeddingProvider = "local"
    embedding_model: str = LOCAL_EMBEDDING_MODEL
    openrouter_embedding_model: Optional[str] = None

    def get_database_url(self) -> str:
        """
        Return the database URL or Capy's project-local SQLite path.

        If no database URL is configured, creates the local ``data`` directory
        and stores the database in ``data/capy_memory.db``.
        """
        if self.database_url:
            return self.database_url

        db_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(db_dir, exist_ok=True)
        return f"sqlite:///{os.path.join(db_dir, 'capy_memory.db')}"

    def get_api_key(self) -> str:
        """Get the API key for the configured LLM provider."""
        if self.llm_provider == "openrouter":
            if not self.openrouter_api_key:
                raise RuntimeError(
                    "OpenRouter API key is required when using openrouter provider. "
                    "Set OPENROUTER_API_KEY in the environment."
                )
            return self.openrouter_api_key

        if not self.general_compute_api_key:
            raise RuntimeError(
                "General Compute API key is required. "
                "Set GENERAL_COMPUTE_API_KEY in the environment."
            )
        return self.general_compute_api_key

    def get_base_url(self) -> Optional[str]:
        """Get the base URL for the configured LLM provider."""
        if self.llm_provider == "openrouter":
            return "https://openrouter.ai/api/v1"
        return self.general_compute_base_url.rstrip("/")

    def validate(self) -> None:
        """Validate essential provider settings."""
        if self.llm_provider not in ("general_compute", "openrouter"):
            raise RuntimeError("LLM_PROVIDER must be general_compute or openrouter.")
        if self.embedding_provider not in ("local", "openrouter"):
            raise RuntimeError("EMBEDDING_PROVIDER must be local or openrouter.")

        self.get_api_key()
        if not self.get_base_url():
            raise RuntimeError("The configured LLM base URL must not be empty.")
        if not self.llm_model.strip():
            raise RuntimeError("LLM_MODEL must not be empty.")
        if self.embedding_provider == "openrouter":
            if not self.openrouter_api_key:
                raise RuntimeError(
                    "OpenRouter API key is required for OpenRouter embeddings. "
                    "Set OPENROUTER_API_KEY in the environment."
                )
            if not self.openrouter_embedding_model:
                raise RuntimeError(
                    "OPENROUTER_EMBEDDING_MODEL is required for OpenRouter embeddings."
                )


# Global singleton for settings
_settings: Optional[CapySettings] = None


def configure(
    general_compute_api_key: Optional[str] = None,
    database_url: Optional[str] = None,
    debug: bool = False,
    llm_provider: LLMProvider = "general_compute",
    general_compute_base_url: str = GENERAL_COMPUTE_BASE_URL,
    openrouter_api_key: Optional[str] = None,
    llm_model: str = "gpt-oss-120b",
    embedding_provider: EmbeddingProvider = "local",
    embedding_model: str = LOCAL_EMBEDDING_MODEL,
    openrouter_embedding_model: Optional[str] = None,
) -> None:
    """
    Initialize Capy configuration.

    Args:
        general_compute_api_key: Required for the General Compute provider.
        database_url: Optional database connection URL. By default Capy uses
                      ``data/capy_memory.db`` in the project.
        debug: Optional flag for verbose database connection output.
        llm_provider: Chat provider: ``general_compute`` or ``openrouter``.
        general_compute_base_url: OpenAI-compatible General Compute endpoint.
        openrouter_api_key: Required for OpenRouter chat or embeddings.
        llm_model: Chat model. Defaults to ``gpt-oss-120b``.
        embedding_provider: ``local`` by default; ``openrouter`` is optional.
        embedding_model: Local or provider embedding model name.
        openrouter_embedding_model: OpenRouter embedding model when selected.
    """
    global _settings
    _settings = CapySettings(
        general_compute_api_key=general_compute_api_key,
        database_url=database_url,
        debug=debug,
        llm_provider=llm_provider,
        general_compute_base_url=general_compute_base_url,
        openrouter_api_key=openrouter_api_key,
        llm_model=llm_model,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        openrouter_embedding_model=openrouter_embedding_model,
    )


def get_settings() -> CapySettings:
    """
    Get current settings.

    If configure() has not been called, loads settings from environment variables.
    """
    global _settings

    if _settings is None:
        # Load .env file if it exists
        load_dotenv()

        general_compute_key = os.environ.get("GENERAL_COMPUTE_API_KEY")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        database_url = os.environ.get("DATABASE_URL")
        debug = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

        llm_provider = os.environ.get("LLM_PROVIDER", "general_compute")
        if llm_provider not in ("general_compute", "openrouter"):
            llm_provider = "general_compute"

        embedding_provider = os.environ.get("EMBEDDING_PROVIDER", "local")
        if embedding_provider not in ("local", "openrouter"):
            embedding_provider = "local"

        _settings = CapySettings(
            general_compute_api_key=general_compute_key,
            database_url=database_url,
            debug=debug,
            llm_provider=llm_provider,
            general_compute_base_url=os.environ.get(
                "GENERAL_COMPUTE_BASE_URL", GENERAL_COMPUTE_BASE_URL
            ),
            openrouter_api_key=openrouter_key,
            llm_model=os.environ.get("LLM_MODEL", "gpt-oss-120b"),
            embedding_provider=embedding_provider,
            embedding_model=os.environ.get("EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL),
            openrouter_embedding_model=os.environ.get("OPENROUTER_EMBEDDING_MODEL"),
        )

    return _settings


def reset_settings() -> None:
    """
    Reset settings to None. Useful for testing.
    """
    global _settings
    _settings = None
