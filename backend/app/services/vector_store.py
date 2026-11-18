from __future__ import annotations

import logging
import threading
from typing import Any, Iterable

import numpy as np

from ..config import Settings
from ..db import Database

logger = logging.getLogger(__name__)


class VectorStore:
    def add(
        self,
        project_id: str,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        raise NotImplementedError

    def query(self, project_id: str, embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def delete_document(self, document_id: str) -> None:
        raise NotImplementedError

    def count(self, project_id: str | None = None) -> int:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()
        self._client = None
        self._collection = None
        self._error: str | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            import chromadb

            self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.settings.chroma_path))
            self._collection = self._client.get_or_create_collection(
                name="hypercortex_chunks",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Chroma vector store ready at %s", self.settings.chroma_path)
        except Exception as exc:
            self._error = str(exc)
            logger.warning("Chroma unavailable (%s), will use SQLite vector fallback", exc)

    @property
    def available(self) -> bool:
        return self._collection is not None

    def add(
        self,
        project_id: str,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        if not self.available or not chunks:
            return
        ids = [chunk["id"] for chunk in chunks]
        metadatas = [
            {
                "project_id": project_id,
                "document_id": document_id,
                "filename": chunk.get("filename", ""),
                "page": int(chunk["page"]) if chunk.get("page") is not None else -1,
                "section": chunk.get("section", ""),
                "chunk_index": int(chunk.get("chunk_index", 0)),
            }
            for chunk in chunks
        ]
        with self._lock:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=[chunk["content"] for chunk in chunks],
                metadatas=metadatas,
            )

    def query(self, project_id: str, embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        if not self.available:
            return []
        with self._lock:
            result = self._collection.query(
                query_embeddings=[embedding],
                n_results=max(1, top_k),
                where={"project_id": project_id},
                include=["documents", "metadatas", "distances"],
            )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        items: list[dict[str, Any]] = []
        for index, chunk_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            score = max(0.0, min(1.0, 1.0 - distance))
            items.append(
                {
                    "id": chunk_id,
                    "content": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "score": score,
                }
            )
        return items

    def delete_document(self, document_id: str) -> None:
        if not self.available:
            return
        with self._lock:
            try:
                self._collection.delete(where={"document_id": document_id})
            except Exception as exc:
                logger.warning("Could not delete Chroma vectors for %s: %s", document_id, exc)

    def count(self, project_id: str | None = None) -> int:
        if not self.available:
            return 0
        try:
            if project_id:
                result = self._collection.get(where={"project_id": project_id}, include=[])
                return len(result.get("ids", []))
            return int(self._collection.count())
        except Exception:
            return 0

    def health(self) -> dict[str, Any]:
        return {
            "type": "chroma",
            "available": self.available,
            "path": str(self.settings.chroma_path),
            "error": self._error,
        }


class SQLiteVectorStore(VectorStore):
    def __init__(self, db: Database):
        self.db = db
        self._lock = threading.RLock()

    def add(
        self,
        project_id: str,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        vectors: list[tuple[str, str, str, bytes]] = []
        for chunk, embedding in zip(chunks, embeddings):
            vector = np.asarray(embedding, dtype=np.float32)
            vectors.append(
                (
                    chunk["id"],
                    project_id,
                    document_id,
                    vector.tobytes(),
                )
            )
        with self._lock:
            self.db.store_vectors(vectors)

    def query(self, project_id: str, embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        rows = self.db.get_vectors_for_project(project_id)
        if not rows:
            return []
        query_vector = np.asarray(embedding, dtype=np.float32)
        query_norm = float(np.linalg.norm(query_vector)) or 1.0
        scored: list[tuple[float, str]] = []
        for chunk_id, raw in rows:
            vector = np.frombuffer(raw, dtype=np.float32)
            if vector.shape != query_vector.shape:
                continue
            norm = float(np.linalg.norm(vector)) or 1.0
            score = float(np.dot(vector, query_vector) / (norm * query_norm))
            scored.append((score, chunk_id))
        scored.sort(reverse=True)
        return [
            {"id": chunk_id, "content": "", "metadata": {}, "score": max(0.0, min(1.0, score))}
            for score, chunk_id in scored[: max(1, top_k)]
        ]

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            self.db.delete_vectors_for_document(document_id)

    def count(self, project_id: str | None = None) -> int:
        if project_id:
            return len(self.db.get_vectors_for_project(project_id))
        return self.db.count_chunks()

    def health(self) -> dict[str, Any]:
        return {"type": "sqlite", "available": True}


def create_vector_store(settings: Settings, db: Database) -> VectorStore:
    if settings.vector_store.lower() == "sqlite":
        return SQLiteVectorStore(db)
    chroma = ChromaVectorStore(settings)
    if chroma.available:
        return chroma
    logger.warning("Falling back to SQLite vector store")
    return SQLiteVectorStore(db)
