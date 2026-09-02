from capy.core.openai import get_openai_client
from capy.core.settings import configure, get_settings


def test_capy_provider_defaults(offline_settings):
    """The default test configuration uses the assigned Capy providers."""
    assert offline_settings.llm_provider == "general_compute"
    assert offline_settings.llm_model == "gpt-oss-120b"
    assert offline_settings.get_base_url() == "https://api.generalcompute.com/v1"
    assert offline_settings.embedding_provider == "local"
    assert offline_settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"


def test_llm_client_uses_general_compute_endpoint(offline_settings):
    """The OpenAI-compatible client points at General Compute."""
    client = get_openai_client()

    assert str(client.base_url).rstrip("/") == "https://api.generalcompute.com/v1"


def test_explicit_sqlite_path_creates_parent_directory(tmp_path):
    """An explicit SQLite file URL works when its parent is new."""
    database_path = tmp_path / "nested" / "capy.db"
    configure(
        general_compute_api_key="test-key",
        database_url=f"sqlite:///{database_path}",
    )

    settings = get_settings()
    assert settings.get_database_url() == f"sqlite:///{database_path}"
    assert database_path.parent.exists()
