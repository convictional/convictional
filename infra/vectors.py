import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from openai import AsyncOpenAI

from config import settings
from config.settings import EmbeddingBackend

MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION: int = 1536
_CACHE_DIR = Path("tmp/embedding_cache")


class EmbeddingClient(ABC):
    @abstractmethod
    async def embed(self, text: str, dimensions: int = EMBEDDING_DIMENSION) -> list[float]:
        pass


class OpenAIEmbeddingClient(EmbeddingClient):
    async def embed(self, text: str, dimensions: int = EMBEDDING_DIMENSION) -> list[float]:
        api_key = settings.openai_api_key.get_secret_value()
        organization = settings.openai_organization
        async with AsyncOpenAI(api_key=api_key, organization=organization) as openai_client:
            response = await openai_client.embeddings.create(input=[text], model=MODEL, dimensions=dimensions)

            data = response.data[0]
            if not data:
                raise ValueError("No embedding data returned from OpenAI")
            return data.embedding


class FakeEmbeddingClient(EmbeddingClient):
    async def embed(self, text: str, dimensions: int = EMBEDDING_DIMENSION) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        vector = np.random.default_rng(seed).standard_normal(dimensions)
        norm = np.linalg.norm(vector)
        if norm:
            vector = vector / norm
        return vector.tolist()


class CachedEmbeddingClient(EmbeddingClient):
    def __init__(self, client: EmbeddingClient):
        self._client = client

    async def embed(self, text: str, dimensions: int = EMBEDDING_DIMENSION) -> list[float]:
        key = hashlib.sha256(f"{text}:{dimensions}".encode()).hexdigest()
        cache_file = _CACHE_DIR / f"{key}.npy"
        model_file = _CACHE_DIR / ".model"

        if model_file.exists() and model_file.read_text().strip() == MODEL and cache_file.exists():
            return np.load(cache_file).tolist()

        result = await self._client.embed(text, dimensions)

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if not model_file.exists() or model_file.read_text().strip() != MODEL:
            model_file.write_text(MODEL)
        np.save(cache_file, np.array(result, dtype=np.float32))
        return result


def create_embedding_client() -> EmbeddingClient:
    if settings.embedding_backend == EmbeddingBackend.FAKE:
        return FakeEmbeddingClient()
    openai_client = OpenAIEmbeddingClient()
    if settings.embedding_backend == EmbeddingBackend.CACHED_OPENAI:
        return CachedEmbeddingClient(openai_client)
    return openai_client


@dataclass
class Vectors:
    async def embed(self, text: str, dimensions: int = EMBEDDING_DIMENSION) -> list[float]:
        # Resolve per call so a test-time settings.override() takes effect (mirrors
        # how infra.push selects its delivery backend from current settings).
        return await create_embedding_client().embed(text, dimensions)


def cosine_similarity(first: list[float], second: list[float]) -> float:
    first_array = np.array(first)
    second_array = np.array(second)

    # Check for invalid values (NaN, inf)
    if not (np.isfinite(first_array).all() and np.isfinite(second_array).all()):
        return 0.0

    # Calculate norms
    first_norm = np.linalg.norm(first_array)
    second_norm = np.linalg.norm(second_array)

    # Handle zero vectors
    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0

    # Calculate cosine similarity
    return np.dot(first_array, second_array) / (first_norm * second_norm)
