"""
LLM client management with lazy initialization.

Supports multiple providers:
- general_compute: General Compute's OpenAI-compatible API
- openrouter: OpenRouter's OpenAI-compatible API
"""

from openai import OpenAI

from capy.core.settings import get_settings

# Global clients (lazy initialized)
_llm_client = None
_embedding_client = None


def get_llm_client() -> OpenAI:
    """
    Get or create the LLM client based on the configured provider.

    Uses lazy initialization - the client is created on the first call.

    Returns:
        OpenAI-compatible client instance.

    Raises:
        RuntimeError: If the required API key is not configured.
    """
    global _llm_client
    if _llm_client is None:
        settings = get_settings()
        settings.validate()

        if settings.llm_provider == "openrouter":
            _llm_client = OpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.get_base_url(),
                default_headers={
                    "HTTP-Referer": "https://github.com/capy-companion",
                    "X-Title": "Capy",
                },
            )
        else:
            _llm_client = OpenAI(
                api_key=settings.general_compute_api_key,
                base_url=settings.get_base_url(),
            )

    return _llm_client


def get_embedding_client() -> OpenAI:
    """
    Get or create the optional OpenRouter embedding client.

    Capy defaults to local embeddings, so this client is only available when
    ``EMBEDDING_PROVIDER=openrouter`` is explicitly configured.

    Returns:
        OpenAI-compatible client instance for embeddings.

    Raises:
        RuntimeError: If local embeddings are selected or the required key is absent.
    """
    global _embedding_client
    if _embedding_client is None:
        settings = get_settings()
        if settings.embedding_provider != "openrouter":
            raise RuntimeError(
                "Local embeddings are configured. Use the local embedding implementation "
                "instead of get_embedding_client()."
            )
        settings.validate()
        _embedding_client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/capy-companion",
                "X-Title": "Capy",
            },
        )

    return _embedding_client


# Backward compatibility alias
def get_openai_client() -> OpenAI:
    """
    Backward-compatible alias for get_llm_client().

    Returns:
        OpenAI-compatible client instance.
    """
    return get_llm_client()


def reset_client() -> None:
    """
    Reset all clients to None. Useful for testing.
    """
    global _llm_client, _embedding_client
    _llm_client = None
    _embedding_client = None
