"""页面级向量索引（可选能力）。

存成 `.llm-wiki/vectors.json`：页面规模是百页级，直接浮点数组 + numpy 余弦足够，
比引入外部向量库更可控，也便于随项目一起打包迁移。
"""

from __future__ import annotations

import base64
import math
from typing import Any

import numpy as np

from ..services.embeddings import EmbeddingService
from .store import WikiWorkspace, sha256_text


class PageVectorIndex:
    def __init__(self, workspace: WikiWorkspace, embeddings: EmbeddingService):
        self.workspace = workspace
        self.embeddings = embeddings

    def _load(self) -> dict[str, Any]:
        data = self.workspace.read_json(".llm-wiki/vectors.json", {"entries": {}})
        return data if isinstance(data, dict) and isinstance(data.get("entries"), dict) else {"entries": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.workspace.write_json(".llm-wiki/vectors.json", data)

    @staticmethod
    def _encode(vector: list[float]) -> str:
        array = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(array))
        if norm > 0:
            array = array / norm
        return base64.b64encode(array.tobytes()).decode("ascii")

    @staticmethod
    def _decode(blob: str) -> np.ndarray:
        raw = base64.b64decode(blob.encode("ascii"))
        return np.frombuffer(raw, dtype=np.float32)

    def upsert(self, relative: str, text: str) -> None:
        digest = sha256_text(text)
        data = self._load()
        entries = data["entries"]
        if entries.get(relative, {}).get("hash") == digest:
            return
        vector = self.embeddings.embed_documents([text[:6000]])
        if not vector:
            return
        entries[relative] = {"hash": digest, "vector": self._encode(vector[0])}
        self._save(data)

    def upsert_page(self, relative: str) -> None:
        """按页面路径重建向量（手工编辑、问答回存后调用）。"""
        record = self.workspace.page_record(relative)
        self.upsert(record.path, f"{record.title}\n{record.body}")

    def remove(self, relative: str) -> None:
        data = self._load()
        if relative in data["entries"]:
            data["entries"].pop(relative, None)
            self._save(data)

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        data = self._load()
        entries = data["entries"]
        if not entries:
            return []
        query_vector = np.asarray(self.embeddings.embed_query(query), dtype=np.float32)
        norm = float(np.linalg.norm(query_vector))
        if norm <= 0:
            return []
        query_vector = query_vector / norm
        scored: list[tuple[str, float]] = []
        for relative, entry in entries.items():
            try:
                vector = self._decode(str(entry.get("vector") or ""))
            except (ValueError, TypeError):
                continue
            if vector.size != query_vector.size:
                continue
            score = float(np.dot(query_vector, vector))
            if math.isfinite(score):
                scored.append((relative, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def count(self) -> int:
        return len(self._load().get("entries") or {})
