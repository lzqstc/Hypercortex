from __future__ import annotations

import logging
import math
import threading
from typing import Any

from ..config import Settings
from .bm25 import tokenize
from .retrieval_types import RetrievedChunk

logger = logging.getLogger(__name__)


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    maximum = max(values)
    if maximum <= 0:
        return [0.0 for _ in values]
    return [value / maximum for value in values]


class Reranker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._load_failed = False
        self._lock = threading.RLock()

    def _load_model(self):
        if not self.settings.rerank_model or self._load_failed:
            return None
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None or self._load_failed:
                return self._model
            try:
                from sentence_transformers import CrossEncoder

                logger.info("Loading reranker model %s", self.settings.rerank_model)
                self._model = CrossEncoder(self.settings.rerank_model, device=self.settings.embedding_device)
                logger.info("Reranker model loaded")
            except Exception as exc:
                self._load_failed = True
                logger.warning("Could not load reranker model %s: %s", self.settings.rerank_model, exc)
            return self._model

    def _neural_rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[float] | None:
        model = self._load_model()
        if model is None:
            return None
        try:
            pairs = [(query, candidate.content) for candidate in candidates]
            scores = model.predict(pairs)
            result = []
            for score in scores:
                value = float(score)
                result.append(1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, value)))))
            return result
        except Exception as exc:
            logger.warning("Reranker inference failed, falling back to heuristic: %s", exc)
            return None

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        if not self.settings.rerank_enabled:
            for candidate in candidates:
                candidate.final_score = candidate.rrf_score
            return candidates

        rrf_scores = _normalize([candidate.rrf_score for candidate in candidates])
        vector_scores = _normalize([candidate.vector_score for candidate in candidates])
        neural = self._neural_rerank(query, candidates)
        query_tokens = set(tokenize(query))
        query_lower = query.lower().strip()

        for index, candidate in enumerate(candidates):
            if neural is not None:
                candidate.rerank_score = neural[index]
                candidate.final_score = (
                    0.72 * candidate.rerank_score
                    + 0.18 * rrf_scores[index]
                    + 0.10 * vector_scores[index]
                )
                continue

            content_lower = candidate.content.lower()
            chunk_tokens = set(tokenize(f"{candidate.section}\n{candidate.content}"))
            overlap = (
                len(query_tokens & chunk_tokens) / len(query_tokens) if query_tokens else 0.0
            )
            phrase_bonus = 1.0 if query_lower and query_lower in content_lower else 0.0
            section_overlap = (
                len(query_tokens & set(tokenize(candidate.section))) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            candidate.rerank_score = (
                0.46 * rrf_scores[index]
                + 0.28 * vector_scores[index]
                + 0.17 * overlap
                + 0.05 * phrase_bonus
                + 0.04 * section_overlap
            )
            candidate.final_score = candidate.rerank_score

        return sorted(candidates, key=lambda item: item.final_score, reverse=True)

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.rerank_enabled,
            "model": self.settings.rerank_model or "heuristic",
            "loaded": self._model is not None,
            "fallback": bool(self.settings.rerank_model and self._load_failed),
        }
