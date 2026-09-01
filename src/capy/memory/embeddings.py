from typing import List

from capy.core.openai import get_embedding_client
from capy.core.settings import get_settings

# Global local model (lazy initialized)
_local_embedding_model = None


def embed_text(text: str) -> List[float]:
    """
    Generate an embedding for text.

    Local SentenceTransformer embeddings are used by default and do not require
    API credits. OpenRouter embeddings are used only when explicitly selected.
    """
    settings = get_settings()

    if settings.embedding_provider == "local":
        global _local_embedding_model
        if _local_embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError(
                    "Local embeddings require sentence-transformers. "
                    "Install the project dependencies first."
                ) from error
            _local_embedding_model = SentenceTransformer(settings.embedding_model)

        embedding = _local_embedding_model.encode(text, normalize_embeddings=True)
        return [float(value) for value in embedding]

    client = get_embedding_client()

    # OpenRouter requires the provider prefix for embedding models.
    model = settings.openrouter_embedding_model or settings.embedding_model
    if not model.startswith("openai/"):
        model = f"openai/{model}"

    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding
