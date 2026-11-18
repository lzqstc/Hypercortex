from __future__ import annotations

import hashlib
import logging
import threading
from typing import Iterable

import httpx
import numpy as np

from ..config import Settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.embedding_provider.lower().strip()
        self.model_name = settings.embedding_model
        self._model = None
        self._local_failed = False
        self._lock = threading.RLock()
        self._dimension = settings.embedding_dim if hasattr(settings, "embedding_dim") else 512
        self._hash_dim = 512

    @property
    def dimension(self) -> int:
        if self.provider == "local" and self._model is not None:
            return int(self._model.get_sentence_embedding_dimension())
        if self.provider == "openai":
            return int(getattr(self.settings, "embedding_dimension", 1536))
        return self._hash_dim

    def _load_local_model(self):
        if self._model is not None or self._local_failed:
            return self._model
        with self._lock:
            if self._model is not None or self._local_failed:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model %s on %s", self.model_name, self.settings.embedding_device)
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.settings.embedding_device,
                    trust_remote_code=False,
                )
                logger.info("Embedding model loaded, dimension=%s", self._model.get_sentence_embedding_dimension())
            except Exception as exc:
                self._local_failed = True
                logger.warning(
                    "Could not load local embedding model %s (%s). Falling back to hash embeddings.",
                    self.model_name,
                    exc,
                )
            return self._model

    def _local_embed(self, texts: list[str], is_query: bool) -> list[list[float]]:
        model = self._load_local_model()
        if model is None:
            return [self._hash_embed(text) for text in texts]
        prefix = self.settings.embedding_query_prefix if is_query else ""
        values = [f"{prefix}{text}" if prefix else text for text in texts]
        vectors = model.encode(
            values,
            batch_size=self.settings.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        api_key = self.settings.embedding_api_key or self.settings.llm_api_key
        if not api_key:
            raise RuntimeError("EMBEDDING_API_KEY 未配置")
        url = f"{self.settings.embedding_base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": self.settings.embedding_api_model, "input": texts}
        with httpx.Client(timeout=60) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in items]

    def _hash_embed(self, text: str) -> list[float]:
        normalized = text.lower().strip()
        vector = np.zeros(self._hash_dim, dtype=np.float32)
        if not normalized:
            return vector.tolist()
        for n in (1, 2, 3):
            for index in range(max(0, len(normalized) - n + 1)):
                token = normalized[index : index + n]
                if not token.strip():
                    continue
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                position = int.from_bytes(digest[:4], "little") % self._hash_dim
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[position] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        values = [text for text in texts if text and text.strip()]
        if not values:
            return []
        if self.provider == "openai":
            try:
                return self._openai_embed(values)
            except Exception as exc:
                logger.warning("OpenAI embedding failed, falling back to hash embeddings: %s", exc)
                return [self._hash_embed(text) for text in values]
        if self.provider == "local":
            return self._local_embed(values, is_query=False)
        return [self._hash_embed(text) for text in values]

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self.dimension
        if self.provider == "openai":
            try:
                return self._openai_embed([text])[0]
            except Exception as exc:
                logger.warning("OpenAI query embedding failed, falling back to hash embeddings: %s", exc)
                return self._hash_embed(text)
        if self.provider == "local":
            return self._local_embed([text], is_query=True)[0]
        return self._hash_embed(text)

    def health(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model_name if self.provider != "hash" else "hash-ngram",
            "loaded": self._model is not None,
            "fallback": self._local_failed if self.provider == "local" else self.provider == "hash",
            "dimension": self.dimension,
        }
