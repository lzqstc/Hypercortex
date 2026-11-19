"""Wiki / 深度研究 API。

路径前缀统一为 `/api/wiki`，与前端 `services/api.ts` 的 wiki 客户端一一对应。
所有写操作都会把工作区注册到摄取服务，保证后台队列能持续消费。
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services.parsers import ParserError, parse_file
from .chat import ChatService
from .graph import build_graph
from .ingest import IngestService, document_payload
from .lint import lint_labels, run_lint
from .llm import LLMBridge
from .research import DeepResearchService
from .search import WikiSearcher, context_budget
from .store import (
    SYSTEM_PAGES,
    TYPE_LABELS,
    WikiWorkspace,
    build_frontmatter,
    copy_source_file,
    normalize_body,
    parse_frontmatter,
    safe_slug,
    today,
    workspace_for,
)
from .templates import resolve_template, template_list
from .vectors import PageVectorIndex

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class SettingsPatch(BaseModel):
    language: str | None = None
    autoIngest: bool | None = None
    vectorSearch: bool | None = None
    contextTokens: int | None = Field(default=None, ge=4000, le=1000000)
    historyDepth: int | None = Field(default=None, ge=2, le=40)
    reviewPolicy: str | None = None


class PurposePayload(BaseModel):
    content: str = ""


class IngestPayload(BaseModel):
    paths: list[str] = Field(default_factory=list)
    force: bool = False


class PagePayload(BaseModel):
    path: str = ""
    content: str = ""
    type: str = "concept"
    title: str = ""
    body: str = ""


class SearchPayload(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=30)
    include_sources: bool = True
    expand: bool = True


class ChatPayload(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    sessionId: str | None = None
    mode: str = "balanced"


class SessionPayload(BaseModel):
    title: str = "新对话"


class RenamePayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class SavePayload(BaseModel):
    question: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class ResearchPayload(BaseModel):
    topic: str = Field(min_length=2, max_length=600)
    seedPages: list[str] = Field(default_factory=list)
    autoIngest: bool = True


class ReviewAction(BaseModel):
    action: str = "Skip"


class ReviewBatch(BaseModel):
    ids: list[str] = Field(default_factory=list)
    action: str = "Skip"


class InitPayload(BaseModel):
    template: str = "research"


# ---------------------------------------------------------------------------
# 依赖
# ---------------------------------------------------------------------------


def _state(request: Request):
    return request.app.state


def _project(request: Request, project_id: str | None) -> dict[str, Any]:
    pid = project_id or "default"
    project = _state(request).db.get_project(pid)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在：{pid}")
    return project


def _workspace(request: Request, project_id: str | None, *, ensure: bool = False) -> WikiWorkspace:
    project = _project(request, project_id)
    workspace = workspace_for(_state(request).settings, project["id"], project["name"])
    if ensure:
        workspace.ensure(resolve_template(project.get("template")))
    _state(request).wiki_ingest.register(workspace)
    return workspace


def _ingest(request: Request) -> IngestService:
    return _state(request).wiki_ingest


def _research(request: Request) -> DeepResearchService:
    return _state(request).wiki_research


def _chat(request: Request) -> ChatService:
    return _state(request).wiki_chat


def _reindex_vector(request: Request, workspace: WikiWorkspace, relative: str) -> None:
    """手工编辑页面后同步向量索引；索引不可用时静默跳过。"""
    try:
        if not workspace.settings().get("vectorSearch", True):
            return
        PageVectorIndex(workspace, _state(request).embeddings).upsert_page(relative)
    except Exception as exc:  # noqa: BLE001
        logger.debug("vector reindex skipped for %s: %s", relative, exc)


# ---------------------------------------------------------------------------
# 项目 / 概览
# ---------------------------------------------------------------------------


@router.get("/templates")
def list_templates() -> dict[str, Any]:
    return {"items": template_list()}


@router.get("/projects")
def list_projects(request: Request) -> dict[str, Any]:
    """返回 HyperCortex 项目 + 各自 wiki 规模。前端用它判断是否需要初始化。"""
    items: list[dict[str, Any]] = []
    for project in _state(request).db.list_projects():
        workspace = workspace_for(_state(request).settings, project["id"], project["name"])
        _ingest(request).register(workspace)
        counts = workspace.counts() if workspace.exists() else {"sources": 0, "pages": 0, "reviews": 0}
        items.append(
            {
                "id": project["id"],
                "name": project["name"],
                "template": project.get("template") or "",
                "exists": workspace.exists(),
                "path": str(workspace.root),
                "counts": counts,
            }
        )
    return {"items": items}


@router.post("/projects/{project_id}/init")
def init_project(request: Request, project_id: str, payload: InitPayload | None = None) -> dict[str, Any]:
    project = _project(request, project_id)
    template = resolve_template((payload.template if payload else "") or project.get("template"))
    workspace = workspace_for(_state(request).settings, project["id"], project["name"])
    workspace.ensure(template)
    workspace.update_settings({"template": template.id})
    workspace.append_log("init", project["name"], f"初始化工作区（模板：{template.name}）")
    _ingest(request).register(workspace)
    return {
        "item": {
            "id": project["id"],
            "name": project["name"],
            "template": template.id,
            "templateName": template.name,
            "exists": True,
            "path": str(workspace.root),
            "counts": workspace.counts(),
        }
    }


@router.get("/overview")
def overview(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    exists = workspace.exists()
    records = [
        record for record in workspace.page_records(include_body=False) if record.path not in SYSTEM_PAGES
    ] if exists else []
    by_type: dict[str, int] = {}
    for record in records:
        by_type[record.type or "other"] = by_type.get(record.type or "other", 0) + 1
    lint = run_lint(workspace) if exists else {"issues": [], "stats": {"pages": 0, "errors": 0, "warnings": 0, "health": 0}}
    queue = _ingest(request).queue(workspace.project_id) if exists else []
    settings = workspace.settings() if exists else {}
    return {
        "project": {
            "id": workspace.project_id,
            "name": workspace.project_name,
            "path": str(workspace.root),
            "exists": exists,
        },
        "counts": {
            "sources": len(workspace.source_files()) if exists else 0,
            "pages": len(records),
            "reviews": len([item for item in workspace.reviews() if not item.get("resolved")]) if exists else 0,
            "lintErrors": lint["stats"]["errors"],
            "lintWarnings": lint["stats"]["warnings"],
            "queue": len([item for item in queue if item.get("status") in {"queued", "running"}]),
        },
        "health": lint["stats"].get("health", 0),
        "byType": [
            {"type": key, "label": TYPE_LABELS.get(key, key), "count": value}
            for key, value in sorted(by_type.items(), key=lambda item: -item[1])
        ],
        "purpose": workspace.purpose()[:1200] if exists else "",
        "queue": queue,
        "settings": settings,
        "llm": LLMBridge(_state(request).settings).health(),
    }


@router.get("/purpose")
def get_purpose(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"content": workspace.purpose()}


@router.put("/purpose")
def set_purpose(request: Request, payload: PurposePayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    workspace.set_purpose(payload.content)
    return {"ok": True}


@router.get("/schema")
def get_schema(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"content": workspace.schema()}


@router.put("/schema")
def set_schema(request: Request, payload: PurposePayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    workspace.set_schema(payload.content)
    return {"ok": True}


@router.get("/settings")
def get_settings_api(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"item": workspace.settings()}


@router.patch("/settings")
def patch_settings(request: Request, payload: SettingsPatch, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    return {"item": workspace.update_settings(payload.model_dump(exclude_none=True))}


# ---------------------------------------------------------------------------
# 来源
# ---------------------------------------------------------------------------


@router.get("/sources")
def list_sources(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        return {"project": {"id": workspace.project_id, "name": workspace.project_name, "exists": False}, "items": []}
    return {
        "project": {"id": workspace.project_id, "name": workspace.project_name, "exists": True},
        "items": workspace.source_items(),
    }


@router.post("/sources/upload")
async def upload_sources(
    request: Request,
    files: list[UploadFile] = File(...),
    project: str = Form("default"),
) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    settings = _state(request).settings
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个文件")
    saved: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        for upload in files:
            name = Path(upload.filename or "未命名文件").name
            extension = Path(name).suffix.lower()
            if extension not in settings.allowed_extension_set:
                await upload.close()
                raise HTTPException(status_code=415, detail=f"不支持的文件类型：{extension or '未知'}")
            temp_path = Path(temp_dir) / f"{uuid.uuid4().hex}{extension}"
            size = 0
            with temp_path.open("wb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        await upload.close()
                        raise HTTPException(status_code=413, detail=f"《{name}》超过 {settings.max_upload_mb} MB")
                    handle.write(chunk)
            await upload.close()
            relative = copy_source_file(workspace, temp_path, name)
            saved.append(relative)
    tasks = _ingest(request).enqueue(workspace, saved)
    return {"items": saved, "tasks": tasks}


@router.post("/sources/import")
def import_documents(request: Request, project: str | None = None) -> dict[str, Any]:
    """把知识库里已解析的文档复制进 raw/sources，随后统一编译。"""
    project_item = _project(request, project)
    workspace = _workspace(request, project_item["id"], ensure=True)
    documents = _state(request).db.list_documents(project_item["id"])
    saved: list[str] = []
    missing: list[str] = []
    for document in documents:
        stored = document.get("stored_path")
        if not stored or not Path(stored).is_file():
            missing.append(document["filename"])
            continue
        saved.append(copy_source_file(workspace, Path(stored), document["filename"]))
    tasks = _ingest(request).enqueue(workspace, saved) if saved else []
    return {"items": saved, "missing": missing, "tasks": tasks}


@router.delete("/sources")
def delete_source(request: Request, path: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    try:
        result = workspace.delete_source(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="来源文件不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.get("/source/content")
def source_content(request: Request, path: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    try:
        text, name = document_payload(workspace, path, _state(request).settings)
    except (OSError, ParserError) as exc:
        raise HTTPException(status_code=400, detail=f"无法解析该资料：{exc}") from exc
    return {"name": name, "content": text[:200000], "chars": len(text)}


# ---------------------------------------------------------------------------
# 摄取队列
# ---------------------------------------------------------------------------


@router.post("/ingest")
def ingest(request: Request, payload: IngestPayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    if not payload.paths:
        paths = [path.relative_to(workspace.root).as_posix() for path in workspace.source_files()]
    else:
        paths = payload.paths
    if not paths:
        raise HTTPException(status_code=400, detail="没有可编译的来源，请先导入资料")
    tasks = _ingest(request).enqueue(workspace, paths, force=payload.force)
    return {"items": tasks}


@router.get("/queue")
def queue(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"items": _ingest(request).queue(workspace.project_id)}


@router.post("/queue/{task_id}/cancel")
def cancel_task(request: Request, task_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not _ingest(request).cancel(workspace.project_id, task_id):
        raise HTTPException(status_code=404, detail="任务不存在或已结束")
    return {"ok": True}


@router.post("/queue/{task_id}/retry")
def retry_task(request: Request, task_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not _ingest(request).retry(workspace.project_id, task_id):
        raise HTTPException(status_code=400, detail="只有失败或已取消的任务可以重试")
    return {"ok": True}


@router.post("/rebuild")
def rebuild(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        raise HTTPException(status_code=400, detail="工作区尚未初始化")
    workspace.rebuild_index()
    workspace.rebuild_overview()
    return {"ok": True, "index": workspace.read_text("wiki/index.md")[:400], "overview": workspace.read_text("wiki/overview.md")[:400]}


@router.post("/reset")
def reset(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    workspace.clear_pages()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


@router.get("/pages")
def list_pages(request: Request, project: str | None = None, type: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        return {"items": [], "types": []}
    records = workspace.page_records(include_body=True)
    if type:
        records = [record for record in records if record.type == type]
    items = [record.summary() for record in records if record.path not in SYSTEM_PAGES]
    type_counts: dict[str, int] = {}
    for item in items:
        type_counts[item["type"] or "other"] = type_counts.get(item["type"] or "other", 0) + 1
    return {
        "items": items,
        "types": [
            {"type": key, "label": TYPE_LABELS.get(key, key), "count": value}
            for key, value in sorted(type_counts.items(), key=lambda item: -item[1])
        ],
    }


@router.get("/page")
def read_page(request: Request, file: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    try:
        record = workspace.page_record(file)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="页面不存在") from None
    graph = build_graph(workspace)
    return {
        "path": record.path,
        "meta": record.meta,
        "content": record.body.strip(),
        "raw": workspace.read_text(record.path),
        "related": graph.related(record.name, limit=6),
        "backlinks": [
            {"id": node, "title": graph.by_id[node].title} for node in sorted(graph.backlinks.get(record.name, ()))
        ],
    }


@router.post("/page")
def save_page(request: Request, payload: PagePayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    if payload.path:
        try:
            target = workspace.path(payload.path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="页面不存在")
        meta, _ = parse_frontmatter(target.read_text(encoding="utf-8", errors="ignore"))
        meta["updated"] = today()
        content = payload.content
        if not content.lstrip().startswith("---"):
            content = build_frontmatter(meta) + "\n" + normalize_body(content)
        workspace.write_text(payload.path, content)
        workspace.rebuild_index()
        workspace.rebuild_overview()
        _reindex_vector(request, workspace, payload.path)
        return {"ok": True, "path": payload.path}
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="请填写页面标题")
    relative = workspace.write_page(
        payload.type or "concept",
        title,
        payload.body or f"# {title}\n\n",
        tags=["手工创建"],
        sources=[],
        slug=safe_slug(title),
    )
    workspace.rebuild_index()
    workspace.rebuild_overview()
    _reindex_vector(request, workspace, relative)
    return {"ok": True, "path": relative}


@router.delete("/page")
def delete_page(request: Request, file: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.delete_page(file):
        raise HTTPException(status_code=404, detail="页面不存在")
    workspace.rebuild_index()
    workspace.rebuild_overview()
    try:
        PageVectorIndex(workspace, _state(request).embeddings).remove(file)
    except Exception:  # noqa: BLE001 - 向量索引只是增强，失败不影响删除
        pass
    return {"ok": True}


# ---------------------------------------------------------------------------
# 图谱 / 检索
# ---------------------------------------------------------------------------


@router.get("/graph")
def graph(
    request: Request,
    project: str | None = None,
    type: str | None = None,
    q: str = "",
    limit: int = Query(default=400, ge=10, le=1200),
) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        return {"nodes": [], "edges": [], "communities": [], "stats": {"pages": 0, "links": 0, "density": 0}}
    wiki = build_graph(workspace)
    return wiki.export(limit=limit, node_type=type, query=q)


@router.get("/insights")
def insights(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        return {"surprising": [], "gaps": []}
    wiki = build_graph(workspace)
    wiki.detect_communities()
    return {"surprising": wiki.surprising_connections(6), "gaps": wiki.knowledge_gaps(8)}


@router.get("/related")
def related(request: Request, id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    wiki = build_graph(workspace)
    if id not in wiki.by_id:
        raise HTTPException(status_code=404, detail="节点不存在")
    return {"items": wiki.related(id, limit=12)}


@router.post("/search")
def search(request: Request, payload: SearchPayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        return {"items": [], "context": "", "citations": []}
    searcher = WikiSearcher(workspace)
    hits = searcher.search(
        payload.query,
        limit=payload.limit,
        graph=build_graph(workspace),
        include_sources=payload.include_sources,
        expand=payload.expand,
    )
    budget = context_budget(workspace.settings().get("contextTokens") or 32000)
    context, citations = searcher.build_context(hits, max_chars=min(budget["pages"], 12000))
    return {
        "items": [hit.as_dict() for hit in hits],
        "citations": citations,
        "context": context[:6000],
        "budget": budget,
    }


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


@router.get("/sessions")
def list_sessions(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"items": _chat(request).list_sessions(workspace)}


@router.post("/sessions")
def create_session(request: Request, payload: SessionPayload | None = None, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    return {"item": _chat(request).create_session(workspace, (payload.title if payload else "新对话"))}


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"item": _chat(request).get_session(workspace, session_id)}


@router.patch("/sessions/{session_id}")
def rename_session(request: Request, session_id: str, payload: RenamePayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    item = _chat(request).rename_session(workspace, session_id, payload.title)
    if not item:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"item": item}


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    _chat(request).delete_session(workspace, session_id)
    return {"ok": True}


@router.post("/chat")
def chat(request: Request, payload: ChatPayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        raise HTTPException(status_code=400, detail="工作区尚未初始化，请先初始化并导入资料")
    try:
        return _chat(request).ask(workspace, payload.question, session_id=payload.sessionId, mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chat/save")
def save_chat(request: Request, payload: SavePayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    path = _chat(request).save_to_wiki(workspace, payload.question, payload.answer, payload.citations)
    workspace.rebuild_index()
    workspace.rebuild_overview()
    return {"ok": True, "path": path}


# ---------------------------------------------------------------------------
# 深度研究
# ---------------------------------------------------------------------------


@router.get("/research")
def list_research(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return {"items": _research(request).list_tasks(workspace)}


@router.post("/research")
async def start_research(request: Request, payload: ResearchPayload, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    try:
        task = await _research(request).start(
            workspace,
            payload.topic,
            seed_pages=payload.seedPages,
            auto_ingest=payload.autoIngest,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": task}


@router.get("/research/{task_id}")
def get_research(request: Request, task_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    task = _research(request).get_task(workspace, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    return {"item": task}


# ---------------------------------------------------------------------------
# 质检 / 审阅
# ---------------------------------------------------------------------------


@router.get("/lint")
def lint(request: Request, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    if not workspace.exists():
        return {"issues": [], "stats": {"pages": 0, "errors": 0, "warnings": 0, "health": 0}, "labels": lint_labels()}
    result = run_lint(workspace)
    result["labels"] = lint_labels()
    return result


@router.get("/reviews")
def reviews(request: Request, project: str | None = None, include_resolved: bool = False) -> dict[str, Any]:
    workspace = _workspace(request, project)
    items = workspace.reviews() if workspace.exists() else []
    if not include_resolved:
        items = [item for item in items if not item.get("resolved")]
    return {"items": items[:200], "total": len(items)}


# 注意：批量路由必须声明在 /reviews/{review_id} 之前，否则 "resolve" 会被当成 id
@router.post("/reviews/resolve")
def resolve_reviews(request: Request, payload: ReviewBatch, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    return workspace.resolve_reviews(payload.ids, payload.action)


@router.post("/reviews/{review_id}")
def resolve_review(request: Request, review_id: str, payload: ReviewAction, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project)
    item = workspace.resolve_review(review_id, payload.action)
    if not item:
        raise HTTPException(status_code=404, detail="审核项不存在")
    return {"item": item}


@router.post("/reviews/{review_id}/create-page")
def review_create_page(request: Request, review_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    item = next((entry for entry in workspace.reviews() if entry.get("id") == review_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="审核项不存在")
    title = str(item.get("title") or "待建页面")
    body = "\n".join(
        [
            f"# {title}",
            "",
            f"> 由审阅项创建 · {today()}",
            "",
            "## 待补充",
            "",
            str(item.get("description") or "（审阅项没有给出说明）"),
            "",
            "## 检索线索",
            "",
            *[f"- {query}" for query in item.get("searchQueries") or []],
            "",
        ]
    )
    relative = workspace.write_page("query", title, body, tags=["待建"], slug=safe_slug(title))
    workspace.resolve_review(review_id, "Create Page")
    workspace.rebuild_index()
    workspace.rebuild_overview()
    _reindex_vector(request, workspace, relative)
    return {"ok": True, "path": relative}


@router.post("/reviews/{review_id}/research")
async def review_research(request: Request, review_id: str, project: str | None = None) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    item = next((entry for entry in workspace.reviews() if entry.get("id") == review_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="审核项不存在")
    topic = str(item.get("title") or "")
    queries = item.get("searchQueries") or []
    if queries:
        topic = f"{topic}（{'；'.join(queries[:2])}）"
    task = await _research(request).start(workspace, topic[:200], auto_ingest=True)
    workspace.resolve_review(review_id, "Deep Research")
    return {"item": task}


# ---------------------------------------------------------------------------
# 导出 / 导入
# ---------------------------------------------------------------------------


@router.get("/export")
def export_project(request: Request, project: str | None = None) -> StreamingResponse:
    workspace = _workspace(request, project, ensure=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in workspace.root.rglob("*"):
            if path.is_file() and ".tmp" not in path.name:
                archive.write(path, path.relative_to(workspace.root).as_posix())
    buffer.seek(0)
    # 中文项目名无法直接放进 Content-Disposition（HTTP 头只能 latin-1），
    # 按 RFC 5987 同时给出 ASCII 回退名与 UTF-8 名称。
    stem = safe_slug(workspace.project_name) or workspace.project_id
    filename = f"{stem}-wiki.zip"
    fallback = f"{safe_slug(workspace.project_id) or 'wiki'}-wiki.zip"
    disposition = f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


@router.post("/import")
def import_project(
    request: Request,
    file: UploadFile = File(...),
    project: str = Form("default"),
) -> dict[str, Any]:
    workspace = _workspace(request, project, ensure=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "project.zip"
        with archive_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    continue
                archive.extract(member, workspace.root)
    workspace.rebuild_index()
    workspace.rebuild_overview()
    return {"ok": True}
