import math

from capy.memory.embeddings import embed_text


def test_local_embedding_model_generates_normalized_vector(offline_settings):
    """The configured local model returns a normalized 384-dimensional vector."""
    embedding = embed_text("Capy remembers that the user likes tea.")

    norm = math.sqrt(sum(value * value for value in embedding))
    assert len(embedding) == 384
    assert math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5)
