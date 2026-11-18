from __future__ import annotations

import logging
import re
from collections import defaultdict

from ..config import Settings
from ..db import Database
from .bm25 import BM25IndexManager
from .embeddings import EmbeddingService
from .reranker import Reranker
from .retrieval_types import RetrievedChunk
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


class Retriever:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        bm25: BM25IndexManager,
        reranker: Reranker,
    ):
        self.settings = settings
        self.db = db
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.bm25 = bm25
        self.reranker = reranker

    def search(
        self, project_id: str, query: str, top_k: int = 6
    ) -> tuple[list[RetrievedChunk], bool]:
        query = query.strip()
        if not query:
            return [], True

        query_embedding = self.embeddings.embed_query(query)
        dense_results = self.vector_store.query(
            project_id=project_id,
            embedding=query_embedding,
            top_k=self.settings.dense_top_k,
        )
        sparse_results = self.bm25.search(
            project_id=project_id,
            query=query,
            top_k=self.settings.bm25_top_k,
        )

        if not dense_results and not sparse_results:
            return [], True

        rrf_scores: dict[str, float] = defaultdict(float)
        dense_scores: dict[str, float] = {}
        sparse_scores: dict[str, float] = {}

        for rank, item in enumerate(dense_results):
            chunk_id = item["id"]
            rrf_scores[chunk_id] += 1.0 / (60 + rank + 1)
            dense_scores[chunk_id] = max(dense_scores.get(chunk_id, 0.0), float(item.get("score", 0.0)))

        for rank, item in enumerate(sparse_results):
            chunk_id = item.chunk_id
            rrf_scores[chunk_id] += 1.0 / (60 + rank + 1)
            sparse_scores[chunk_id] = max(sparse_scores.get(chunk_id, 0.0), float(item.score))

        rows = self.db.get_chunks_by_ids(list(rrf_scores.keys()))
        row_by_id = {row["id"]: row for row in rows}
        candidates: list[RetrievedChunk] = []
        for chunk_id, rrf_score in rrf_scores.items():
            row = row_by_id.get(chunk_id)
            if not row:
                continue
            candidates.append(
                RetrievedChunk(
                    id=row["id"],
                    document_id=row["document_id"],
                    project_id=row["project_id"],
                    filename=row["filename"],
                    page=row["page"],
                    section=row["section"] or "",
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    vector_score=dense_scores.get(chunk_id, 0.0),
                    sparse_score=sparse_scores.get(chunk_id, 0.0),
                    rrf_score=rrf_score,
                    source_url=row.get("source_url"),
                )
            )

        candidates = self.reranker.rerank(query, candidates)
        selected: list[RetrievedChunk] = []
        skipped: list[RetrievedChunk] = []
        seen_content: set[str] = set()
        per_document: dict[str, int] = defaultdict(int)

        for candidate in candidates:
            normalized = _WHITESPACE.sub("", candidate.content)[:160]
            if normalized in seen_content:
                continue
            if candidate.final_score < self.settings.min_relevance_score:
                continue
            if per_document[candidate.document_id] >= self.settings.max_chunks_per_document:
                skipped.append(candidate)
                continue
            seen_content.add(normalized)
            per_document[candidate.document_id] += 1
            selected.append(candidate)
            if len(selected) >= top_k:
                break

        if len(selected) < top_k:
            for candidate in skipped:
                normalized = _WHITESPACE.sub("", candidate.content)[:160]
                if normalized in seen_content:
                    continue
                seen_content.add(normalized)
                selected.append(candidate)
                if len(selected) >= top_k:
                    break

        selected = selected[:top_k]
        low_confidence = not selected or selected[0].final_score < self.settings.min_relevance_score
        logger.info(
            "Retrieved project=%s query=%r dense=%s sparse=%s selected=%s low_confidence=%s",
            project_id,
            query[:80],
            len(dense_results),
            len(sparse_results),
            len(selected),
            low_confidence,
        )
        return selected, low_confidence
