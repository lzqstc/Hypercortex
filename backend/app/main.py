from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import get_settings
from .db import Database
from .services.bm25 import BM25IndexManager
from .services.embeddings import EmbeddingService
from .services.ingestion import IngestionService
from .services.llm import LLMService
from .services.rag import RAGService
from .services.reranker import Reranker
from .services.retriever import Retriever
from .services.vector_store import create_vector_store
from .wiki.api import router as wiki_router
from .wiki.chat import ChatService
from .wiki.ingest import IngestService
from .wiki.research import DeepResearchService

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
INDEX_FILE = FRONTEND_DIST / "index.html"
ASSETS_DIR = FRONTEND_DIST / "assets"


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.uploads_path.mkdir(parents=True, exist_ok=True)

    db = Database(settings.db_path)
    db.init_schema()
    embeddings = EmbeddingService(settings)
    vector_store = create_vector_store(settings, db)
    bm25 = BM25IndexManager(db)
    reranker = Reranker(settings)
    retriever = Retriever(settings, db, embeddings, vector_store, bm25, reranker)
    llm = LLMService(settings)
    rag = RAGService(settings, db, retriever, llm)
    ingestion = IngestionService(settings, db, embeddings, vector_store, bm25)

    wiki_ingest = IngestService(settings, embeddings)
    wiki_research = DeepResearchService(settings)
    wiki_chat = ChatService(wiki_ingest.llm)
    # 启动即注册所有项目工作区，保证重启后遗留的编译任务会被继续消费
    from .wiki.store import workspace_for

    for project in db.list_projects():
        wiki_ingest.register(workspace_for(settings, project["id"], project["name"]))

    app.state.settings = settings
    app.state.db = db
    app.state.embeddings = embeddings
    app.state.vector_store = vector_store
    app.state.bm25 = bm25
    app.state.reranker = reranker
    app.state.retriever = retriever
    app.state.llm = llm
    app.state.rag = rag
    app.state.ingestion = ingestion
    app.state.wiki_ingest = wiki_ingest
    app.state.wiki_research = wiki_research
    app.state.wiki_chat = wiki_chat

    await ingestion.start()
    if settings.wiki_enabled:
        await wiki_ingest.start()
    logger.info(
        "HyperCortex RAG API ready: data=%s vector=%s embedding=%s llm=%s wiki=%s",
        settings.data_path,
        vector_store.health().get("type"),
        settings.embedding_provider,
        settings.llm_provider,
        "on" if settings.wiki_enabled else "off",
    )
    try:
        yield
    finally:
        if settings.wiki_enabled:
            await wiki_ingest.stop()
        await ingestion.stop()
        logger.info("HyperCortex RAG API stopped")


app = FastAPI(
    title="HyperCortex RAG API",
    version="1.0.0",
    description="企业知识库 RAG 后端：多格式解析、混合检索、重排、引用与问答。",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
    if request.url.path != "/api/health":
        logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "请求参数不合法", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "服务内部错误，请稍后重试"})


@app.get("/", include_in_schema=False)
async def root():
    if INDEX_FILE.is_file():
        return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-cache"})
    return {
        "service": "hypercortex-rag-api",
        "docs": "/docs",
        "health": "/api/health",
    }


app.include_router(router)
app.include_router(wiki_router)


# 生产模式：由 FastAPI 同源托管前端构建产物（frontend/dist）
if INDEX_FILE.is_file():
    if ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-cache"})
