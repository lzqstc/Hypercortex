from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/wiki", tags=["wiki"])

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
SKIP_PAGES = {"index", "log", "overview"}
PAGE_DIRS = {
    "entities": "entity",
    "concepts": "concept",
    "sources": "source",
    "queries": "query",
    "synthesis": "synthesis",
    "comparisons": "comparison",
    "findings": "finding",
    "methodology": "methodology",
    "thesis": "thesis",
}


class ReviewAction(BaseModel):
    action: str = "Skip"


# --------------------------------------------------------------------------
# 路径解析：Windows 盘符 -> WSL /mnt/<drive>，应用状态目录自动探测
# --------------------------------------------------------------------------


def _to_local(raw: str) -> Path:
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw or "")
    if match and os.name != "nt":
        return Path(f"/mnt/{match.group(1).lower()}/{match.group(2).replace(chr(92), '/')}")
    return Path(raw)


def _app_state_file() -> Path | None:
    configured = os.environ.get("LLM_WIKI_APP_STATE")
    if configured and Path(configured).is_file():
        return Path(configured)
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "com.llmwiki.app" / "app-state.json"
        if candidate.is_file():
            return candidate
    users = Path("/mnt/c/Users")
    if users.is_dir():
        for entry in sorted(users.iterdir()):
            candidate = entry / "AppData" / "Roaming" / "com.llmwiki.app" / "app-state.json"
            if candidate.is_file():
                return candidate
    return None


def _read_app_state() -> dict[str, Any]:
    path = _app_state_file()
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _projects() -> list[dict[str, Any]]:
    state = _read_app_state()
    items: list[dict[str, Any]] = []
    for entry in state.get("recentProjects") or []:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("path") or "")
        local = _to_local(raw)
        items.append(
            {
                "id": str(entry.get("id") or local.name),
                "name": str(entry.get("name") or local.name),
                "rawPath": raw,
                "path": str(local),
                "exists": local.is_dir(),
            }
        )
    fallback = os.environ.get("LLM_WIKI_PROJECT_PATH")
    if fallback and not items:
        local = _to_local(fallback)
        items.append({"id": local.name, "name": local.name, "rawPath": fallback, "path": str(local), "exists": local.is_dir()})
    return items


def _project(project_id: str | None) -> dict[str, Any]:
    items = _projects()
    if not items:
        raise HTTPException(status_code=404, detail="没有找到 LLM Wiki 项目")
    if not project_id:
        return items[0]
    for item in items:
        if item["id"] == project_id or item["name"] == project_id:
            return item
    raise HTTPException(status_code=404, detail=f"LLM Wiki 项目不存在：{project_id}")


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise HTTPException(status_code=400, detail="非法路径")
    return candidate


# --------------------------------------------------------------------------
# 解析工具
# --------------------------------------------------------------------------


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            meta[key] = [item.strip().strip("'\"") for item in inner.split(",") if item.strip()] if inner else []
        else:
            meta[key] = value.strip("'\"")
    return meta, text[match.end():]


def _page_records(root: Path) -> list[dict[str, Any]]:
    wiki = root / "wiki"
    if not wiki.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(wiki.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        meta, body = _parse_frontmatter(text)
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "name": path.stem,
                "dir": path.parent.name,
                "type": str(meta.get("type") or ""),
                "title": str(meta.get("title") or path.stem),
                "sources": meta.get("sources") if isinstance(meta.get("sources"), list) else [],
                "updated": str(meta.get("updated") or ""),
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
                "meta": meta,
                "body": body,
                "hasFrontmatter": bool(meta),
            }
        )
    return records


def _sources(root: Path) -> list[dict[str, Any]]:
    raw = root / "raw" / "sources"
    if not raw.is_dir():
        return []
    cache: dict[str, Any] = {}
    cache_file = root / ".llm-wiki" / "ingest-cache.json"
    if cache_file.is_file():
        try:
            cache = (json.loads(cache_file.read_text(encoding="utf-8")) or {}).get("entries") or {}
        except (OSError, json.JSONDecodeError):
            cache = {}
    wiki_sources = {item["name"]: item for item in _page_records(root) if item["dir"] == "sources"}
    items: list[dict[str, Any]] = []
    for path in sorted(raw.rglob("*")):
        if not path.is_file():
            continue
        # 跳过 .cache 等隐藏目录中的解析缓存
        if any(part.startswith(".") for part in path.relative_to(raw).parts):
            continue
        relative = path.relative_to(root).as_posix()
        entry = cache.get(path.name) or {}
        wiki_page = wiki_sources.get(path.stem)
        items.append(
            {
                "name": path.name,
                "path": relative,
                "size": path.stat().st_size,
                "ext": path.suffix.lower().lstrip("."),
                "modifiedAt": _iso(path.stat().st_mtime),
                "ingested": bool(entry) or bool(wiki_page),
                "hash": str(entry.get("hash") or ""),
                "wikiPage": wiki_page["path"] if wiki_page else "",
                "wikiPages": len(entry.get("filesWritten") or []),
            }
        )
    return items


def _reading_minutes(chars: int) -> int:
    return max(1, round(chars / 400))


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------


@router.get("/projects")
def list_projects() -> dict[str, Any]:
    items = _projects()
    for item in items:
        root = Path(item["path"])
        if not item["exists"]:
            item["counts"] = {"sources": 0, "pages": 0, "reviews": 0}
            continue
        item["counts"] = {
            "sources": len(_sources(root)),
            "pages": len(_page_records(root)),
            "reviews": len(_pending_reviews(root)),
        }
    return {"items": items}


def _pending_reviews(root: Path) -> list[dict[str, Any]]:
    path = root / ".llm-wiki" / "review.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or []
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and not item.get("resolved")]


@router.get("/overview")
def overview(project: str | None = None) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="项目目录不存在")
    records = _page_records(root)
    sources = _sources(root)
    reviews = _pending_reviews(root)
    lint = _lint(root, records)
    purpose = ""
    purpose_file = root / "purpose.md"
    if purpose_file.is_file():
        purpose = purpose_file.read_text(encoding="utf-8", errors="ignore").strip()[:800]
    return {
        "project": item,
        "counts": {
            "sources": len(sources),
            "pages": len(records),
            "reviews": len(reviews),
            "lintErrors": sum(1 for issue in lint if issue["level"] == "error"),
            "lintWarnings": sum(1 for issue in lint if issue["level"] == "warning"),
        },
        "purpose": purpose,
    }


@router.get("/sources")
def list_sources(project: str | None = None) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="项目目录不存在")
    return {"project": item, "items": _sources(root)}


@router.get("/pages")
def list_pages(project: str | None = None) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="项目目录不存在")
    records = _page_records(root)
    return {
        "project": item,
        "items": [
            {
                "path": record["path"],
                "title": record["title"],
                "type": record["type"],
                "sources": record["sources"],
                "updated": record["updated"],
                "size": record["size"],
                "readingMinutes": _reading_minutes(len(record["body"])),
            }
            for record in records
        ],
    }


@router.get("/page")
def read_page(file: str, project: str | None = None) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    target = _safe_child(root, file)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="页面不存在")
    text = target.read_text(encoding="utf-8", errors="ignore")
    meta, body = _parse_frontmatter(text)
    return {"path": file, "meta": meta, "content": body.strip(), "raw": text}


@router.get("/reviews")
def list_reviews(project: str | None = None, include_resolved: bool = False) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    path = root / ".llm-wiki" / "review.json"
    if not path.is_file():
        return {"project": item, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or []
    except (OSError, json.JSONDecodeError):
        data = []
    items = [entry for entry in data if isinstance(entry, dict)]
    if not include_resolved:
        items = [entry for entry in items if not entry.get("resolved")]
    return {"project": item, "items": items}


@router.post("/reviews/{review_id}")
def resolve_review(review_id: str, payload: ReviewAction, project: str | None = None) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    path = root / ".llm-wiki" / "review.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="审核文件不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or []
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="审核文件无法解析")
    found = None
    for entry in data:
        if isinstance(entry, dict) and entry.get("id") == review_id:
            entry["resolved"] = True
            entry["resolution"] = payload.action
            entry["resolvedAt"] = int(time.time() * 1000)
            found = entry
            break
    if not found:
        raise HTTPException(status_code=404, detail="审核项不存在")
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return {"ok": True, "item": found}


@router.get("/lint")
def lint(project: str | None = None) -> dict[str, Any]:
    item = _project(project)
    root = Path(item["path"])
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="项目目录不存在")
    records = _page_records(root)
    issues = _lint(root, records)
    return {
        "project": item,
        "issues": issues,
        "stats": {
            "pages": len(records),
            "errors": sum(1 for issue in issues if issue["level"] == "error"),
            "warnings": sum(1 for issue in issues if issue["level"] == "warning"),
        },
    }


def _lint(root: Path, records: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    names = {record["name"] for record in records}
    titles = {record["title"] for record in records}
    inbound: dict[str, int] = {name: 0 for name in names}
    source_names = {path.name for path in (root / "raw" / "sources").rglob("*") if path.is_file()} if (root / "raw" / "sources").is_dir() else set()
    index_text = ""
    index_file = root / "wiki" / "index.md"
    if index_file.is_file():
        index_text = index_file.read_text(encoding="utf-8", errors="ignore")

    for record in records:
        if not record["hasFrontmatter"]:
            issues.append({"level": "error", "code": "missing-frontmatter", "file": record["path"], "message": "页面缺少 YAML frontmatter"})
        if not record["title"]:
            issues.append({"level": "warning", "code": "missing-title", "file": record["path"], "message": "frontmatter 缺少 title"})
        if not record["type"]:
            issues.append({"level": "warning", "code": "missing-type", "file": record["path"], "message": "frontmatter 缺少 type"})
        if not record["body"].strip():
            issues.append({"level": "error", "code": "empty-page", "file": record["path"], "message": "页面正文为空"})
        for source in record["sources"]:
            if source not in source_names and Path(str(source)).name not in source_names:
                issues.append(
                    {
                        "level": "error",
                        "code": "missing-source",
                        "file": record["path"],
                        "message": f"引用的原始资料不存在：{source}",
                    }
                )
        for link in WIKILINK_RE.findall(record["body"]):
            target = link.strip()
            if not target:
                continue
            if target in names or target in titles:
                key = target if target in names else next((r["name"] for r in records if r["title"] == target), "")
                if key:
                    inbound[key] = inbound.get(key, 0) + 1
            else:
                issues.append(
                    {
                        "level": "warning",
                        "code": "broken-wikilink",
                        "file": record["path"],
                        "message": f"[[{target}]] 指向不存在的页面",
                    }
                )
        if record["name"] not in SKIP_PAGES and record["path"] != "wiki/index.md":
            if record["name"] not in index_text and record["title"] not in index_text:
                issues.append(
                    {
                        "level": "warning",
                        "code": "not-in-index",
                        "file": record["path"],
                        "message": "index.md 未收录该页面",
                    }
                )

    for record in records:
        if record["name"] in SKIP_PAGES:
            continue
        if inbound.get(record["name"], 0) == 0:
            issues.append(
                {
                    "level": "warning",
                    "code": "orphan-page",
                    "file": record["path"],
                    "message": "孤立页面：没有任何页面链接到它",
                }
            )
    return issues
