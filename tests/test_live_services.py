import pytest

from capy.core.openai import get_openai_client
from capy.memory.embeddings import embed_text


@pytest.mark.live
def test_live_general_compute_and_local_embedding(live_settings):
    """Verify the configured LLM endpoint and local embedding model live."""
    client = get_openai_client()
    response = client.chat.completions.create(
        model=live_settings.llm_model,
        messages=[{"role": "user", "content": "Reply with OK only."}],
        temperature=0,
        max_tokens=2,
    )

    assert response.choices
    assert response.choices[0].message.content

    embedding = embed_text("Capy live embedding check")
    assert embedding
    assert len(embedding) == 384
