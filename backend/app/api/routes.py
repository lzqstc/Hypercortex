from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..models import (
    ChatRequest,
    CloudSyncRequest,
    ProjectCreate,
    ResearchCreate,
    ResearchRun,
    SettingsPatch,
    UrlIngestRequest,
)
from ..services.parsers import ParserError, _validate_public_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _state(request: Request):
    return request.app.state


def _project_or_404(request: Request, project_id: str) -> dict[str, Any]:
    project = _state(request).db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在：{project_id}")
    return project


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {
        "ok": True,
        "service": "hypercortex-rag-api",
        "version": state.settings.app_version,
        "documents": state.db.count_documents(),
        "chunks": state.db.count_chunks(),
        "embedding": state.embeddings.health(),
        "vectorStore": state.vector_store.health(),
        "reranker": state.reranker.health(),
        "llm": state.llm.health(),
        "bm25": state.bm25.health(),
    }


@router.get("/bootstrap")
async def bootstrap(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {
        "projects": state.db.list_projects(),
        "uploads": state.db.list_jobs(limit=20),
        "conversations": state.db.list_conversations(limit=20),
        "researches": state.db.list_researches(limit=20),
        "notifications": state.db.list_notifications(limit=20),
        "settings": state.db.get_settings(),
    }


@router.get("/projects")
async def list_projects(request: Request) -> dict[str, Any]:
    return {"items": _state(request).db.list_projects()}


@router.post("/projects", status_code=201)
async def create_project(request: Request, payload: ProjectCreate) -> dict[str, Any]:
    state = _state(request)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    project = state.db.create_project(
        name=name,
        template=payload.template.strip() or "产品知识库",
        team=payload.team.strip() or "产品与体验中心",
        visibility=payload.visibility.strip() or "团队可见",
    )
    state.db.add_notification("项目创建成功", f"{project['name']} 已创建，可以开始上传资料")
    return {"item": project}


@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: str) -> dict[str, Any]:
    state = _state(request)
    if project_id == "default":
        raise HTTPException(status_code=400, detail="默认知识库不能删除")
    if not state.db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"ok": True}


@router.get("/uploads")
async def list_uploads(request: Request) -> dict[str, Any]:
    return {"items": _state(request).db.list_jobs(limit=30)}


async def _save_upload_files(
    request: Request, files: list[UploadFile], project_id: str
) -> list[dict[str, Any]]:
    state = _state(request)
    settings = state.settings
    _project_or_404(request, project_id)
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个文件")
    if len(files) > settings.max_files_per_job:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {settings.max_files_per_job} 个文件")

    job_directory = settings.uploads_path / uuid.uuid4().hex
    job_directory.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    documents: list[dict[str, Any]] = []

    for upload in files:
        original_name = Path(upload.filename or "未命名文件").name
        extension = Path(original_name).suffix.lower()
        if extension not in settings.allowed_extension_set:
            await upload.close()
            raise HTTPException(
                status_code=415,
                detail=f"不支持的文件类型：{extension or '未知'}，支持 {settings.allowed_extensions}",
            )
        document_id = f"doc_{uuid.uuid4().hex}"
        destination = job_directory / f"{document_id}{extension}"
        hasher = hashlib.sha256()
        size = 0
        try:
            with destination.open("wb") as output:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"文件《{original_name}》超过 {settings.max_upload_mb} MB 限制",
                        )
                    hasher.update(chunk)
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        if size == 0:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"文件《{original_name}》为空")

        documents.append(
            {
                "id": document_id,
                "kind": "file",
                "filename": original_name,
                "stored_path": str(destination),
                "mime": upload.content_type or mimetypes.guess_type(original_name)[0] or "",
                "size": size,
                "sha256": hasher.hexdigest(),
            }
        )
    return documents


@router.post("/uploads", status_code=202)
async def create_upload(
    request: Request,
    project_id: str = Form("default"),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    state = _state(request)
    documents = await _save_upload_files(request, files, project_id)
    job = state.db.create_job(project_id=project_id, job_type="file", documents=documents)
    state.db.add_notification("资料已提交解析", f"{len(documents)} 个文件已进入解析队列")
    state.ingestion.wake()
    return {"item": job}


@router.get("/uploads/{job_id}")
async def get_upload(request: Request, job_id: str) -> dict[str, Any]:
    job = _state(request).db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="上传任务不存在")
    return {"item": job}


@router.post("/uploads/url", status_code=202)
async def ingest_url(request: Request, payload: UrlIngestRequest) -> dict[str, Any]:
    state = _state(request)
    _project_or_404(request, payload.project_id)
    try:
        _validate_public_url(payload.url, state.settings.allow_private_urls)
    except ParserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = urlparse(payload.url)
    filename = f"{parsed.hostname or 'web'}{parsed.path}"[:160] or "网页资料"
    document = {
        "id": f"doc_{uuid.uuid4().hex}",
        "kind": "url",
        "filename": filename,
        "stored_path": None,
        "source_url": payload.url,
        "mime": "text/html",
        "size": 0,
        "sha256": hashlib.sha256(payload.url.encode("utf-8")).hexdigest(),
    }
    job = state.db.create_job(payload.project_id, "url", [document])
    state.db.add_notification("网页已提交解析", payload.url)
    state.ingestion.wake()
    return {"item": job}


@router.post("/uploads/cloud")
async def sync_cloud(_: CloudSyncRequest) -> dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail="云盘同步需要配置钉钉/飞书 OAuth 凭据，当前版本尚未启用；可先使用本地文件或网页链接。",
    )


@router.get("/documents")
async def list_documents(request: Request, project_id: str | None = None) -> dict[str, Any]:
    documents = _state(request).db.list_documents(project_id)
    return {
        "items": [
            {
                "id": document["id"],
                "projectId": document["project_id"],
                "filename": document["filename"],
                "kind": document["kind"],
                "mime": document["mime"],
                "size": document["size"],
                "status": document["status"],
                "progress": document["progress"],
                "pages": document["pages"],
                "chunks": document["chunk_count"],
                "error": document["error"],
                "createdAt": document["created_at"],
                "downloadUrl": (
                    f"/api/documents/{document['id']}/file" if document["stored_path"] else None
                ),
            }
            for document in documents
        ]
    }


@router.get("/documents/{document_id}/file")
async def download_document(request: Request, document_id: str):
    state = _state(request)
    document = state.db.get_document(document_id)
    if not document or not document.get("stored_path"):
        raise HTTPException(status_code=404, detail="文件不存在")
    path = Path(document["stored_path"]).resolve()
    uploads_root = state.settings.uploads_path.resolve()
    if uploads_root not in path.parents:
        raise HTTPException(status_code=403, detail="非法文件路径")
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已被删除")
    return FileResponse(
        path,
        filename=document["filename"],
        media_type=document.get("mime") or None,
        content_disposition_type="inline",
    )


@router.delete("/documents/{document_id}")
async def delete_document(request: Request, document_id: str) -> dict[str, Any]:
    state = _state(request)
    document = state.db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    await asyncio.to_thread(state.vector_store.delete_document, document_id)
    state.db.delete_document(document_id)
    state.bm25.invalidate(document["project_id"])
    stored_path = document.get("stored_path")
    if stored_path:
        Path(stored_path).unlink(missing_ok=True)
    state.db.add_notification("文档已删除", f"《{document['filename']}》及其索引已移除")
    return {"ok": True}


@router.post("/chat")
async def chat(request: Request, payload: ChatRequest) -> dict[str, Any]:
    state = _state(request)
    _project_or_404(request, payload.project_id)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="请输入问题")
    history = [turn.model_dump() for turn in payload.history]
    conversation = await state.rag.ask(
        project_id=payload.project_id,
        question=question,
        top_k=payload.top_k,
        include_citations=payload.include_citations,
        history=history,
    )
    return {"item": conversation}


@router.post("/search")
async def search(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(request)
    project_id = str(payload.get("projectId") or payload.get("project_id") or "default")
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入检索词")
    top_k = max(1, min(20, int(payload.get("topK") or 6)))
    sources, low_confidence = await asyncio.to_thread(
        state.retriever.search, project_id, query, top_k
    )
    return {
        "items": [source.to_source(index + 1) for index, source in enumerate(sources)],
        "lowConfidence": low_confidence,
    }


@router.get("/research")
async def list_research(request: Request, project_id: str | None = None) -> dict[str, Any]:
    return {"items": _state(request).db.list_researches(project_id)}


@router.post("/research", status_code=202)
async def create_research(request: Request, payload: ResearchCreate) -> dict[str, Any]:
    state = _state(request)
    _project_or_404(request, payload.project_id)
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="研究主题不能为空")
    research = state.db.create_research(payload.project_id, topic)
    state.db.add_notification("研究任务已启动", topic)
    return {"item": research}


def _research_or_404(request: Request, research_id: str) -> dict[str, Any]:
    research = _state(request).db.get_research(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    return research


@router.get("/research/{research_id}")
async def get_research(request: Request, research_id: str) -> dict[str, Any]:
    return {"item": _research_or_404(request, research_id)}


@router.post("/research/{research_id}/run")
async def run_research(
    request: Request, research_id: str, payload: ResearchRun | None = None
) -> dict[str, Any]:
    """执行研究：复用 RAG 检索与回答链路，产出可归档的 wiki 结论卡片。"""
    state = _state(request)
    research = _research_or_404(request, research_id)
    topic = (payload.topic.strip() if payload and payload.topic else research["topic"]).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="研究主题不能为空")
    if len(topic) > 2000:
        raise HTTPException(status_code=400, detail="研究主题不能超过 2000 字")

    updated = state.db.update_research(research_id, {"topic": topic, "status": "running"})
    try:
        conversation = await state.rag.ask(
            project_id=research["projectId"],
            question=topic,
            top_k=8,
            include_citations=True,
            history=[],
        )
    except Exception:  # noqa: BLE001 - 统一转成用户可读错误，避免泄露内部细节
        logger.exception("Research run failed: %s", research_id)
        state.db.update_research(research_id, {"status": "failed"})
        raise HTTPException(status_code=502, detail="研究执行失败，请稍后重试或补充资料") from None

    sources = conversation.get("sources") or []
    answer = (conversation.get("answer") or "").strip()
    if not answer:
        state.db.update_research(research_id, {"status": "failed"})
        raise HTTPException(status_code=502, detail="研究未生成有效结论，请补充资料后重试")

    title = topic if len(topic) <= 60 else f"{topic[:60]}…"
    confidence = 0.92 if sources else 0.55
    card = {
        "id": f"card_{uuid.uuid4().hex}",
        "researchId": research_id,
        "projectId": research["projectId"],
        "title": title,
        "content": answer,
        "sources": sources,
        "confidence": confidence,
        "archived": False,
        "createdAt": conversation.get("createdAt") or updated["updatedAt"],
    }
    steps = research.get("steps") or [
        "拆解研究主题",
        "检索并聚类证据",
        "交叉验证矛盾点",
        "生成结构化结论",
        "输出 wiki 卡片",
    ]
    completed = state.db.update_research(
        research_id, {"status": "completed", "steps": steps, "result": card}
    )
    state.db.add_notification("研究结论已生成", topic[:120])
    return {"item": completed}


@router.post("/research/{research_id}/archive")
async def archive_research(request: Request, research_id: str) -> dict[str, Any]:
    state = _state(request)
    research = _research_or_404(request, research_id)
    result = research.get("result")
    if not result:
        raise HTTPException(status_code=400, detail="请先生成研究结论，再归档到知识库")
    if result.get("archived"):
        return {"item": result}
    if not str(result.get("content") or "").strip():
        raise HTTPException(status_code=400, detail="研究结论为空，无法归档")

    card = state.db.create_card(
        project_id=research["projectId"],
        research_id=research_id,
        title=str(result.get("title") or research["topic"]),
        content=str(result.get("content") or ""),
        sources=list(result.get("sources") or []),
        confidence=float(result.get("confidence") or 0),
    )
    result["archived"] = True
    result["id"] = card["id"]
    state.db.update_research(research_id, {"result": result})
    state.db.add_notification("研究结论已归档", card["title"][:120])
    return {"item": card}


@router.get("/cards")
async def list_cards(request: Request, project_id: str | None = None) -> dict[str, Any]:
    return {"items": _state(request).db.list_cards(project_id)}


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return {"item": _state(request).db.get_settings()}


@router.patch("/settings")
async def update_settings(request: Request, payload: SettingsPatch) -> dict[str, Any]:
    settings = _state(request).db.update_settings(payload.as_updates())
    return {"item": settings}


@router.get("/notifications")
async def list_notifications(request: Request) -> dict[str, Any]:
    return {"items": _state(request).db.list_notifications()}


@router.get("/stats")
async def stats(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {
        "projects": len(state.db.list_projects()),
        "documents": state.db.count_documents(),
        "chunks": state.db.count_chunks(),
        "vectors": state.vector_store.count(),
    }
