from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..config import Settings
from ..db import Database
from .llm import LLMService
from .retriever import Retriever

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        retriever: Retriever,
        llm: LLMService,
    ):
        self.settings = settings
        self.db = db
        self.retriever = retriever
        self.llm = llm

    async def ask(
        self,
        project_id: str,
        question: str,
        top_k: int = 6,
        include_citations: bool = True,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        sources, low_confidence = await asyncio.to_thread(
            self.retriever.search,
            project_id,
            question,
            top_k,
        )
        answer, model = await asyncio.to_thread(
            self.llm.answer,
            question,
            sources,
            low_confidence,
            include_citations,
            history or [],
        )
        source_payload = [source.to_source(index + 1) for index, source in enumerate(sources)]
        latency_ms = int((time.perf_counter() - started) * 1000)
        conversation = self.db.create_conversation(
            project_id=project_id,
            question=question,
            answer=answer,
            sources=source_payload,
            model=model,
            latency_ms=latency_ms,
        )
        conversation["lowConfidence"] = low_confidence
        conversation["projectId"] = project_id
        logger.info(
            "RAG answer project=%s question=%r sources=%s low_confidence=%s latency_ms=%s",
            project_id,
            question[:100],
            len(sources),
            low_confidence,
            latency_ms,
        )
        return conversation
