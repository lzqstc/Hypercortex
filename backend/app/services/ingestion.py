from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import Database
from .bm25 import BM25IndexManager
from .chunker import chunk_sections
from .embeddings import EmbeddingService
from .parsers import ParserError, parse_file, parse_url
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        bm25: BM25IndexManager,
    ):
        self.settings = settings
        self.db = db
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.bm25 = bm25
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self.db.reset_stuck_documents()
        for index in range(max(1, self.settings.ingest_workers)):
            self._tasks.append(asyncio.create_task(self._worker(index), name=f"ingest-worker-{index}"))
        logger.info("Started %s ingestion workers", len(self._tasks))

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def wake(self) -> None:
        self._wake_event.set()

    async def _worker(self, index: int) -> None:
        logger.info("Ingestion worker %s started", index)
        while not self._stop_event.is_set():
            document = await asyncio.to_thread(self.db.claim_next_document)
            if not document:
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                self._wake_event.clear()
                continue
            try:
                self.db.update_job(document["job_id"], status="processing")
                await self._process_document(document)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Document ingestion failed: %s", document.get("id"))
                self._mark_failed(document, exc)
        logger.info("Ingestion worker %s stopped", index)

    async def _process_document(self, document: dict[str, Any]) -> None:
        document_id = document["id"]
        job_id = document["job_id"]
        project_id = document["project_id"]
        filename = document["filename"]
        kind = document.get("kind", "file")

        logger.info("Processing document id=%s kind=%s filename=%s", document_id, kind, filename)
        self.db.update_document(document_id, status="processing", progress=5, error=None)

        existing = self.db.find_document_by_hash(
            project_id, document.get("sha256", ""), exclude_id=document_id
        )
        if existing:
            self.db.update_document(
                document_id,
                status="duplicate",
                progress=100,
                error=f"重复文件，已复用《{existing['filename']}》的索引结果",
                chunk_count=0,
            )
            self.db.refresh_job_status(job_id)
            self.db.add_notification(
                "检测到重复文件",
                f"《{filename}》与《{existing['filename']}》内容相同，未重复建立索引",
            )
            return

        if kind == "url":
            sections = await asyncio.to_thread(
                parse_url,
                document.get("source_url") or "",
                self.settings.url_timeout_seconds,
                self.settings.allow_private_urls,
            )
        else:
            stored_path = Path(document.get("stored_path") or "")
            if not stored_path.exists():
                raise ParserError("原始文件不存在，可能已被清理")
            sections = await asyncio.to_thread(
                parse_file,
                stored_path,
                filename,
                self.settings.ocr_enabled,
            )

        if not sections:
            raise ParserError("未能从文件中提取到可检索文本")

        max_page = max((section.page or 0 for section in sections), default=0)
        self.db.update_document(document_id, progress=20, pages=max_page)

        chunks = chunk_sections(
            sections,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
            min_chunk_chars=self.settings.min_chunk_chars,
        )
        if not chunks:
            raise ParserError("文件内容太短，无法生成有效分块")

        records = [
            {
                "id": f"{document_id}:{chunk.index}",
                "document_id": document_id,
                "project_id": project_id,
                "chunk_index": chunk.index,
                "content": chunk.content,
                "page": chunk.page,
                "section": chunk.section,
                "token_count": chunk.token_count,
                "filename": filename,
            }
            for chunk in chunks
        ]

        self.db.update_document(document_id, progress=30, chunk_count=len(records))
        embeddings: list[list[float]] = []
        batch_size = max(1, self.settings.embedding_batch_size)
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            vectors = await asyncio.to_thread(
                self.embeddings.embed_documents,
                [record["content"] for record in batch],
            )
            embeddings.extend(vectors)
            progress = 30 + int(40 * min(1.0, (start + len(batch)) / len(records)))
            self.db.update_document(document_id, progress=progress)

        if len(embeddings) != len(records):
            raise RuntimeError("向量数量与分块数量不一致")

        self.db.insert_chunks(records)
        try:
            await asyncio.to_thread(
                self.vector_store.add,
                project_id,
                document_id,
                records,
                embeddings,
            )
        except Exception:
            logger.exception("Vector indexing failed for document %s; BM25 will still work", document_id)

        self.bm25.invalidate(project_id)
        self.db.update_document(
            document_id,
            status="completed",
            progress=100,
            pages=max_page,
            chunk_count=len(records),
            error=None,
        )
        self.db.refresh_job_status(job_id)
        self.db.add_notification(
            "资料解析完成",
            f"《{filename}》已生成 {len(records)} 个检索片段",
        )
        logger.info("Document completed id=%s chunks=%s", document_id, len(records))

    def _mark_failed(self, document: dict[str, Any], exc: Exception) -> None:
        try:
            self.db.update_document(
                document["id"],
                status="failed",
                progress=0,
                error=str(exc)[:1000],
            )
            self.db.refresh_job_status(document["job_id"])
            self.db.add_notification(
                "资料解析失败",
                f"《{document.get('filename', '未知文件')}》解析失败：{str(exc)[:200]}",
            )
        except Exception:
            logger.exception("Could not persist ingestion failure for %s", document.get("id"))
