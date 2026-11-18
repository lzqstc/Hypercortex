from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    id: str
    document_id: str
    project_id: str
    filename: str
    page: int | None
    section: str
    chunk_index: int
    content: str
    vector_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    source_url: str | None = None

    def to_source(self, rank: int) -> dict:
        return {
            "id": self.id,
            "documentId": self.document_id,
            "title": self.filename,
            "filename": self.filename,
            "sourceUrl": self.source_url,
            "page": self.page,
            "section": self.section,
            "chunkIndex": self.chunk_index,
            "score": round(float(self.final_score), 4),
            "vectorScore": round(float(self.vector_score), 4),
            "rerankScore": round(float(self.rerank_score), 4),
            "rank": rank,
            "snippet": self.content[:320],
            "content": self.content,
        }
