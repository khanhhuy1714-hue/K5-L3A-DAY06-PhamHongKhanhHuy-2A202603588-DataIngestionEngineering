"""Choose a real embedding provider (API or local) and implement this contract."""
import os
from typing import Protocol
from dotenv import load_dotenv
from openai import OpenAI


MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """OpenAI embedding adapter."""

    def __init__(self, model_name: str | None = None, batch_size: int = 64) -> None:
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY in environment or .env file.")

        resolved_model = (model_name or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small").strip()
        if resolved_model not in MODEL_DIMENSIONS:
            raise ValueError(
                f"Unsupported OpenAI embedding model '{resolved_model}'. "
                f"Supported: {list(MODEL_DIMENSIONS.keys())}"
            )

        self.model_name = resolved_model
        self.dimensions = MODEL_DIMENSIONS[resolved_model]
        self.batch_size = batch_size
        self._client = OpenAI(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            response = self._client.embeddings.create(
                model=self.model_name,
                input=batch,
            )
            # Sắp xếp theo index để đảm bảo đúng thứ tự đầu vào
            sorted_data = sorted(response.data, key=lambda item: item.index)
            all_vectors.extend(item.embedding for item in sorted_data)

        return all_vectors

    def embed_query(self, question: str) -> list[float]:
        if not question.strip():
            raise ValueError("question cannot be empty")
        response = self._client.embeddings.create(
            model=self.model_name,
            input=[question],
        )
        return response.data[0].embedding