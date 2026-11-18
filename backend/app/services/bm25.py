from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

import jieba
from rank_bm25 import BM25Okapi

from ..db import Database

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

_STOPWORDS = {
    "的",
    "了",
    "和",
    "是",
    "在",
    "我",
    "有",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "那",
    "什么",
    "怎么",
    "如何",
    "哪些",
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "is",
    "are",
    "for",
    "on",
    "with",
    "as",
    "by",
    "at",
    "be",
    "this",
    "that",
}


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = []
    for word in jieba.lcut_for_search(text):
        word = word.strip()
        if not word or word in _STOPWORDS:
            continue
        if _TOKEN_RE.fullmatch(word):
            tokens.append(word)
    if not tokens:
        tokens = [match.group(0) for match in _TOKEN_RE.finditer(text) if match.group(0) not in _STOPWORDS]
    return tokens


@dataclass
class BM25Hit:
    chunk_id: str
    score: float


class _BM25Index:
    def __init__(self, records: list[dict[str, Any]]):
        self.ids = [record["id"] for record in records]
        self.corpus: list[list[str]] = []
        for record in records:
            text = f"{record.get('section', '')}\n{record.get('content', '')}"
            self.corpus.append(tokenize(text))
        self.bm25 = BM25Okapi(self.corpus) if self.corpus else None

    def search(self, query: str, top_k: int) -> list[BM25Hit]:
        if not self.bm25 or not self.ids:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        ranked = sorted(
            ((float(score), chunk_id) for score, chunk_id in zip(scores, self.ids)),
            reverse=True,
        )
        return [
            BM25Hit(chunk_id=chunk_id, score=max(0.0, score))
            for score, chunk_id in ranked[: max(1, top_k)]
            if score > 0
        ]


class BM25IndexManager:
    def __init__(self, db: Database):
        self.db = db
        self._indexes: dict[str, _BM25Index] = {}
        self._dirty: set[str] = set()
        self._lock = threading.RLock()

    def invalidate(self, project_id: str) -> None:
        with self._lock:
            self._dirty.add(project_id)
            self._indexes.pop(project_id, None)

    def _build(self, project_id: str) -> _BM25Index:
        records = self.db.get_chunks_for_project(project_id)
        logger.info("Building BM25 index for project=%s chunks=%s", project_id, len(records))
        index = _BM25Index(records)
        self._indexes[project_id] = index
        self._dirty.discard(project_id)
        return index

    def search(self, project_id: str, query: str, top_k: int = 30) -> list[BM25Hit]:
        with self._lock:
            index = self._indexes.get(project_id)
            if index is None or project_id in self._dirty:
                index = self._build(project_id)
        return index.search(query, top_k=top_k)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "cached_projects": len(self._indexes),
                "dirty_projects": len(self._dirty),
            }
