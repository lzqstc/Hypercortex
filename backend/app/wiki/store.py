"""工作区存储层：frontmatter、页面索引、来源、索引/日志/总览维护、队列与审核持久化。

所有文件写入都走原子替换，避免进程中断留下半截 markdown；
所有路径解析都限制在项目根目录内，防止 `..` 逃逸。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..config import Settings
from .templates import WikiTemplate, resolve_template

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
SLUG_UNSAFE_RE = re.compile(r"[\\/:*?\"<>|\r\n\t]+")
STRUCTURAL_PAGES = {"index", "log", "overview"}

TYPE_DIRS: dict[str, str] = {
    "entity": "wiki/entities",
    "concept": "wiki/concepts",
    "source": "wiki/sources",
    "query": "wiki/queries",
    "comparison": "wiki/comparisons",
    "synthesis": "wiki/synthesis",
    "thesis": "wiki/thesis",
    "methodology": "wiki/methodology",
    "finding": "wiki/findings",
    "decision": "wiki/decisions",
    "process": "wiki/processes",
    "metric": "wiki/metrics",
    "author": "wiki/authors",
    "overview": "wiki",
}

TYPE_LABELS: dict[str, str] = {
    "entity": "实体",
    "concept": "概念",
    "source": "来源摘要",
    "query": "问题",
    "comparison": "对比",
    "synthesis": "综合",
    "thesis": "论点",
    "methodology": "方法",
    "finding": "发现",
    "decision": "决策",
    "process": "流程",
    "metric": "指标",
    "author": "作者",
    "other": "其他",
    "overview": "总览",
}

SYSTEM_PAGES = ("wiki/index.md", "wiki/log.md", "wiki/overview.md")


def page_excerpt(body: str, limit: int = 60) -> str:
    """取页面正文的第一句可用描述，用于索引与列表摘要。

    跳过标题行、列表符号与「在资料中的含义」这类骨架标题，避免索引里出现
    「低空经济 … 关联 - 来源摘要：… 待补充 -」这样的整段拼接。
    """
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ">", "-", "*", "|", "!", "<!--")):
            continue
        line = re.sub(r"[*_`\[\]]", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 8:
            continue
        sentence = re.split(r"(?<=[。！？；!?;])", line)[0].strip()
        text = sentence if len(sentence) >= 8 else line
        return text[:limit].rstrip() + ("…" if len(text) > limit else "")
    return ""

BASE_DIRS = (
    "raw/sources",
    "raw/assets",
    "wiki/entities",
    "wiki/concepts",
    "wiki/sources",
    "wiki/queries",
    "wiki/comparisons",
    "wiki/synthesis",
    "wiki/media",
    ".llm-wiki/chats",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def today() -> str:
    return date.today().isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def safe_slug(title: str, fallback: str = "untitled") -> str:
    """标题 → 文件名。保留中日韩字符，去掉文件系统非法字符。"""
    raw = SLUG_UNSAFE_RE.sub("-", (title or "").strip())
    raw = re.sub(r"\s+", "-", raw).strip("-.")
    raw = raw[:96].strip("-.")
    return raw or fallback


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items: list[str] = []
        for part in inner.split(","):
            cleaned = _unquote(part.strip())
            if cleaned:
                items.append(cleaned)
        return items
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", "~"}:
        return None
    return _unquote(value)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 YAML-lite frontmatter。失败时返回空元数据与原文，由 lint 报告。"""
    match = FRONTMATTER_RE.match(text.lstrip("\ufeff"))
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_key:
            existing = meta.get(current_key)
            if not isinstance(existing, list):
                existing = []
            existing.append(_unquote(stripped[2:]))
            meta[current_key] = existing
            continue
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        current_key = key
        value = raw_value.strip()
        meta[key] = [] if value == "" else _parse_scalar(value)
    return meta, text[match.end():]


def _yaml_value(value: Any) -> str:
    if isinstance(value, list):
        inner = ", ".join(_quote_if_needed(str(item)) for item in value)
        return f"[{inner}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return _quote_if_needed(str(value))


def _quote_if_needed(value: str) -> str:
    if not value:
        return '""'
    if any(token in value for token in [":", "#", '"', "'", "[", "]", "\n"]):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def build_frontmatter(meta: dict[str, Any]) -> str:
    order = ["type", "title", "tags", "related", "sources", "created", "updated"]
    keys = [key for key in order if key in meta] + [key for key in meta if key not in order]
    lines = ["---"]
    for key in keys:
        value = meta[key]
        if value is None or value == "":
            continue
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def normalize_body(body: str) -> str:
    return body.replace("\r\n", "\n").strip() + "\n"


def extract_links(text: str) -> list[str]:
    return [match.strip() for match in WIKILINK_RE.findall(text) if match.strip()]


@dataclass
class PageRecord:
    path: str
    name: str
    dir: str
    type: str
    title: str
    tags: list[str]
    related: list[str]
    sources: list[str]
    created: str
    updated: str
    size: int
    mtime: float
    body: str
    meta: dict[str, Any]
    has_frontmatter: bool

    def summary(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "dir": self.dir,
            "type": self.type,
            "title": self.title or self.name,
            "tags": self.tags,
            "related": self.related,
            "sources": self.sources,
            "created": self.created,
            "updated": self.updated,
            "size": self.size,
            "readingMinutes": max(1, round(len(self.body) / 400)),
            "excerpt": re.sub(r"\s+", " ", re.sub(r"[#>*`\[\]]", "", self.body))[:180].strip(),
        }


class WikiWorkspace:
    """单个项目的 Wiki 工作区（每个知识库一份，落在 data/wiki/<project_id>）。"""

    def __init__(self, root: Path, project_id: str, project_name: str = ""):
        self.root = root
        self.project_id = project_id
        self.project_name = project_name or project_id
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 基础 IO
    # ------------------------------------------------------------------
    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    @property
    def sources_dir(self) -> Path:
        return self.root / "raw" / "sources"

    @property
    def state_dir(self) -> Path:
        return self.root / ".llm-wiki"

    def path(self, relative: str) -> Path:
        candidate = (self.root / relative.replace("\\", "/")).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("非法路径")
        return candidate

    def exists(self) -> bool:
        return self.wiki_dir.is_dir() and (self.root / "schema.md").is_file()

    def ensure(self, template: WikiTemplate | None = None) -> None:
        with self._lock:
            template = template or resolve_template(None)
            self.root.mkdir(parents=True, exist_ok=True)
            for directory in BASE_DIRS + tuple(template.extra_dirs):
                (self.root / directory).mkdir(parents=True, exist_ok=True)
            self.state_dir.mkdir(parents=True, exist_ok=True)
            (self.state_dir / "chats").mkdir(exist_ok=True)
            (self.root / "raw" / "sources").mkdir(parents=True, exist_ok=True)
            if not (self.root / "purpose.md").is_file():
                self.write_text("purpose.md", template.purpose)
            if not (self.root / "schema.md").is_file():
                self.write_text("schema.md", template.schema)
            if not (self.root / "wiki" / "index.md").is_file():
                self.write_text("wiki/index.md", "# 索引\n\n> 由 HyperCortex 自动维护。\n")
            if not (self.root / "wiki" / "log.md").is_file():
                self.write_text("wiki/log.md", "# 操作日志\n")
            if not (self.root / "wiki" / "overview.md").is_file():
                self.write_text(
                    "wiki/overview.md",
                    "---\ntype: overview\ntitle: 全局总览\n---\n\n# 全局总览\n\n> 尚无已编译内容。导入资料后自动生成。\n",
                )
            self._ensure_state_file("review.json", [])
            self._ensure_state_file("queue.json", [])
            self._ensure_state_file("research.json", [])
            self._ensure_state_file("ingest-cache.json", {"entries": {}})
            self._ensure_state_file("settings.json", {})
            # 与 Obsidian 兼容：wiki 目录可直接作为 vault 打开
            obsidian = self.root / ".obsidian"
            if not (obsidian / "app.json").is_file():
                obsidian.mkdir(parents=True, exist_ok=True)
                self.atomic_write(
                    obsidian / "app.json",
                    json.dumps({"attachmentFolderPath": "raw/assets", "alwaysUpdateLinks": True}, ensure_ascii=False, indent=2),
                )

    def _ensure_state_file(self, name: str, default: Any) -> None:
        target = self.state_dir / name
        if not target.is_file():
            self.atomic_write(target, json.dumps(default, ensure_ascii=False, indent=2))

    @staticmethod
    def atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + f".tmp{os.getpid()}")
        temp.write_text(content, encoding="utf-8", newline="\n")
        temp.replace(target)

    def write_text(self, relative: str, content: str) -> Path:
        target = self.path(relative)
        self.atomic_write(target, content)
        return target

    def read_text(self, relative: str, default: str = "") -> str:
        try:
            return self.path(relative).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return default

    def read_json(self, relative: str, default: Any) -> Any:
        try:
            data = json.loads(self.read_text(relative) or "null")
        except (json.JSONDecodeError, TypeError):
            return default
        return default if data is None else data

    def write_json(self, relative: str, data: Any) -> None:
        self.write_text(relative, json.dumps(data, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------
    # purpose / schema
    # ------------------------------------------------------------------
    def purpose(self) -> str:
        return self.read_text("purpose.md").strip()

    def schema(self) -> str:
        return self.read_text("schema.md").strip()

    def set_purpose(self, text: str) -> None:
        self.write_text("purpose.md", text.strip() + "\n")

    def set_schema(self, text: str) -> None:
        self.write_text("schema.md", text.strip() + "\n")

    # ------------------------------------------------------------------
    # 页面
    # ------------------------------------------------------------------
    def page_records(self, include_body: bool = True) -> list[PageRecord]:
        records: list[PageRecord] = []
        if not self.wiki_dir.is_dir():
            return records
        for path in sorted(self.wiki_dir.rglob("*.md")):
            if path.name.startswith("."):
                continue
            try:
                stat = path.stat()
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            meta, body = parse_frontmatter(text)
            relative = path.relative_to(self.root).as_posix()
            page_type = str(meta.get("type") or "").strip()
            tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
            related = meta.get("related") if isinstance(meta.get("related"), list) else []
            sources = meta.get("sources") if isinstance(meta.get("sources"), list) else []
            records.append(
                PageRecord(
                    path=relative,
                    name=path.stem,
                    dir=path.parent.name,
                    type=page_type,
                    title=str(meta.get("title") or path.stem),
                    tags=[str(item) for item in tags],
                    related=[str(item) for item in related],
                    sources=[str(item) for item in sources],
                    created=str(meta.get("created") or ""),
                    updated=str(meta.get("updated") or ""),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    body=body if include_body else "",
                    meta=meta,
                    has_frontmatter=bool(meta),
                )
            )
        return records

    def page_record(self, relative: str) -> PageRecord:
        path = self.path(relative)
        if not path.is_file():
            raise FileNotFoundError(relative)
        text = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = parse_frontmatter(text)
        stat = path.stat()
        return PageRecord(
            path=path.relative_to(self.root).as_posix(),
            name=path.stem,
            dir=path.parent.name,
            type=str(meta.get("type") or ""),
            title=str(meta.get("title") or path.stem),
            tags=[str(item) for item in (meta.get("tags") or []) if isinstance(meta.get("tags"), list)],
            related=[str(item) for item in (meta.get("related") or []) if isinstance(meta.get("related"), list)],
            sources=[str(item) for item in (meta.get("sources") or []) if isinstance(meta.get("sources"), list)],
            created=str(meta.get("created") or ""),
            updated=str(meta.get("updated") or ""),
            size=stat.st_size,
            mtime=stat.st_mtime,
            body=body,
            meta=meta,
            has_frontmatter=bool(meta),
        )

    def write_page(
        self,
        type: str,
        title: str,
        body: str,
        *,
        tags: Iterable[str] = (),
        related: Iterable[str] = (),
        sources: Iterable[str] = (),
        extra_meta: dict[str, Any] | None = None,
        slug: str | None = None,
    ) -> str:
        directory = TYPE_DIRS.get(type, f"wiki/{type or 'notes'}")
        name = safe_slug(slug or title)
        relative = f"{directory}/{name}.md"
        existing = self.path(relative)
        if existing.is_file():
            meta, old_body = parse_frontmatter(existing.read_text(encoding="utf-8", errors="ignore"))
            merged_sources = sorted({*(str(item) for item in (meta.get("sources") or []) if isinstance(meta.get("sources"), list)), *sources})
            merged_tags = sorted({*(str(item) for item in (meta.get("tags") or []) if isinstance(meta.get("tags"), list)), *tags})
            merged_related = sorted({*(str(item) for item in (meta.get("related") or []) if isinstance(meta.get("related"), list)), *related})
            created = str(meta.get("created") or today())
            meta.update(
                {
                    "type": type,
                    "title": title,
                    "tags": merged_tags,
                    "related": merged_related,
                    "sources": merged_sources,
                    "created": created,
                    "updated": today(),
                }
            )
            if extra_meta:
                meta.update(extra_meta)
            body = self._merge_body(old_body, body)
        else:
            meta = {
                "type": type,
                "title": title,
                "tags": sorted(set(tags)),
                "related": sorted(set(related)),
                "sources": sorted(set(sources)),
                "created": today(),
                "updated": today(),
            }
            if extra_meta:
                meta.update(extra_meta)
        content = build_frontmatter(meta) + "\n" + normalize_body(body)
        self.write_text(relative, content)
        return relative

    @staticmethod
    def _merge_body(old_body: str, new_body: str) -> str:
        """新内容包含旧内容要点时直接替换，否则追加「补充」小节，避免丢失已有信息。"""
        old_clean = old_body.strip()
        new_clean = new_body.strip()
        if not old_clean:
            return new_clean
        if not new_clean:
            return old_clean
        if new_clean in old_clean:
            return old_clean
        if old_clean in new_clean:
            return new_clean
        return f"{old_clean}\n\n## 补充（{today()}）\n\n{new_clean}"

    def delete_page(self, relative: str) -> bool:
        target = self.path(relative)
        if not target.is_file():
            return False
        target.unlink()
        return True

    # ------------------------------------------------------------------
    # 来源
    # ------------------------------------------------------------------
    def source_files(self) -> list[Path]:
        if not self.sources_dir.is_dir():
            return []
        files: list[Path] = []
        for path in sorted(self.sources_dir.rglob("*")):
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(self.sources_dir).parts):
                files.append(path)
        return files

    def ingest_cache(self) -> dict[str, Any]:
        data = self.read_json(".llm-wiki/ingest-cache.json", {"entries": {}})
        if not isinstance(data, dict):
            return {"entries": {}}
        entries = data.get("entries")
        return {"entries": entries if isinstance(entries, dict) else {}}

    def update_ingest_cache(self, source_name: str, payload: dict[str, Any]) -> None:
        with self._lock:
            cache = self.ingest_cache()
            cache["entries"][source_name] = payload
            self.write_json(".llm-wiki/ingest-cache.json", cache)

    def drop_ingest_cache(self, source_name: str) -> None:
        with self._lock:
            cache = self.ingest_cache()
            if source_name in cache["entries"]:
                cache["entries"].pop(source_name, None)
                self.write_json(".llm-wiki/ingest-cache.json", cache)

    def source_items(self) -> list[dict[str, Any]]:
        cache = self.ingest_cache()["entries"]
        summary_pages = {
            record.name: record
            for record in self.page_records(include_body=False)
            if record.dir == "sources"
        }
        items: list[dict[str, Any]] = []
        for path in self.source_files():
            stat = path.stat()
            entry = cache.get(path.name) or {}
            page = summary_pages.get(path.stem)
            items.append(
                {
                    "name": path.name,
                    "path": path.relative_to(self.root).as_posix(),
                    "size": stat.st_size,
                    "ext": path.suffix.lower().lstrip("."),
                    "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "ingested": bool(entry) or bool(page),
                    "hash": str(entry.get("hash") or ""),
                    "wikiPage": page.path if page else "",
                    "wikiPages": len(entry.get("filesWritten") or []),
                    "ingestedAt": str(entry.get("ingestedAt") or ""),
                }
            )
        return items

    # ------------------------------------------------------------------
    # 索引 / 日志 / 总览
    # ------------------------------------------------------------------
    def rebuild_index(self) -> str:
        records = [
            record
            for record in self.page_records(include_body=True)
            if record.path not in SYSTEM_PAGES
        ]
        grouped: dict[str, list[PageRecord]] = {}
        for record in records:
            grouped.setdefault(record.type or "other", []).append(record)
        order = list(TYPE_LABELS)
        lines = ["# 索引", "", f"> 共 {len(records)} 页 · 由 HyperCortex 自动生成（{today()}）", ""]
        for page_type in sorted(grouped, key=lambda item: (order.index(item) if item in order else 99, item)):
            entries = sorted(grouped[page_type], key=lambda item: item.title)
            lines.append(f"## {TYPE_LABELS.get(page_type, page_type)}（{len(entries)}）")
            lines.append("")
            for record in entries:
                excerpt = page_excerpt(record.body)
                suffix = f" — {excerpt}" if excerpt else ""
                lines.append(f"- [[{record.title}]]{suffix}")
            lines.append("")
        content = "\n".join(lines).rstrip() + "\n"
        self.write_text("wiki/index.md", content)
        return content

    def append_log(self, action: str, title: str, detail: str) -> None:
        with self._lock:
            current = self.read_text("wiki/log.md") or "# 操作日志\n"
            header = f"## {today()}"
            entry = f"- {action} | {title} | {detail}"
            if header in current:
                current = current.replace(header, f"{header}\n\n{entry}", 1)
            else:
                body = current.replace("# 操作日志", "").strip()
                current = f"# 操作日志\n\n{header}\n\n{entry}\n" + (f"\n{body}\n" if body else "")
            self.write_text("wiki/log.md", current if current.endswith("\n") else current + "\n")

    def rebuild_overview(self) -> str:
        records = [
            record
            for record in self.page_records(include_body=False)
            if record.path not in SYSTEM_PAGES
        ]
        sources = self.source_files()
        inbound: dict[str, int] = {}
        for record in records:
            for link in extract_links(record.body or self.read_text(record.path)):
                inbound[link] = inbound.get(link, 0) + 1
        by_type: dict[str, int] = {}
        for record in records:
            by_type[record.type or "other"] = by_type.get(record.type or "other", 0) + 1
        top = sorted(records, key=lambda item: (inbound.get(item.title, 0), inbound.get(item.name, 0)), reverse=True)[:8]
        recent = sorted(records, key=lambda item: item.mtime, reverse=True)[:6]
        purpose_first = ""
        for line in self.purpose().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
                purpose_first = stripped
                break
        lines = [
            "---",
            "type: overview",
            "title: 全局总览",
            "---",
            "",
            "# 全局总览",
            "",
            f"> {purpose_first or self.project_name}",
            "",
            "## 规模",
            "",
            f"- 原始资料：{len(sources)} 份",
            f"- 知识页面：{len(records)} 页",
            f"- 页面分布：{'、'.join(f'{TYPE_LABELS.get(key, key)} {value}' for key, value in sorted(by_type.items())) or '暂无'}",
            "",
            "## 当前主线",
            "",
        ]
        if top:
            for record in top:
                lines.append(f"- [[{record.title}]]（{inbound.get(record.name, 0) + inbound.get(record.title, 0)} 处引用）")
        else:
            lines.append("- 尚未编译任何页面")
        lines.extend(["", "## 最近更新", ""])
        if recent:
            for record in recent:
                lines.append(f"- [[{record.title}]] · {record.updated or date.fromtimestamp(record.mtime).isoformat()}")
        else:
            lines.append("- 暂无")
        lines.extend(
            [
                "",
                "## 维护提示",
                "",
                "- 本页由系统在每次编译后重新生成，请勿手工编辑",
                "- 待审阅项与质检结果见「审阅 / 质检」面板",
                "",
            ]
        )
        content = "\n".join(lines)
        self.write_text("wiki/overview.md", content)
        return content

    # ------------------------------------------------------------------
    # 审核项
    # ------------------------------------------------------------------
    def reviews(self) -> list[dict[str, Any]]:
        data = self.read_json(".llm-wiki/review.json", [])
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def add_reviews(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        with self._lock:
            existing = self.reviews()
            seen = {(item.get("type"), item.get("title")) for item in existing}
            for item in items:
                key = (item.get("type"), item.get("title"))
                if key in seen:
                    continue
                seen.add(key)
                item.setdefault("id", f"rev_{int(time.time() * 1000)}_{len(existing)}")
                item.setdefault("createdAt", utcnow())
                item.setdefault("resolved", False)
                item.setdefault("options", [{"label": "建立页面", "action": "Create Page"}, {"label": "跳过", "action": "Skip"}])
                existing.append(item)
            self.write_json(".llm-wiki/review.json", existing)

    def resolve_review(self, review_id: str, action: str) -> dict[str, Any] | None:
        with self._lock:
            items = self.reviews()
            found = None
            for item in items:
                if item.get("id") == review_id:
                    item["resolved"] = True
                    item["resolution"] = action
                    item["resolvedAt"] = utcnow()
                    found = item
                    break
            if found:
                self.write_json(".llm-wiki/review.json", items)
            return found

    def resolve_reviews(self, ids: list[str], action: str) -> dict[str, Any]:
        with self._lock:
            items = self.reviews()
            idset = set(ids)
            resolved = 0
            for item in items:
                if item.get("id") in idset and not item.get("resolved"):
                    item["resolved"] = True
                    item["resolution"] = action
                    item["resolvedAt"] = utcnow()
                    resolved += 1
            self.write_json(".llm-wiki/review.json", items)
            return {"resolved": resolved, "count": len(ids)}

    # ------------------------------------------------------------------
    # 队列
    # ------------------------------------------------------------------
    def queue(self) -> list[dict[str, Any]]:
        data = self.read_json(".llm-wiki/queue.json", [])
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def save_queue(self, items: list[dict[str, Any]]) -> None:
        with self._lock:
            self.write_json(".llm-wiki/queue.json", items)

    # ------------------------------------------------------------------
    # 设置
    # ------------------------------------------------------------------
    def settings(self) -> dict[str, Any]:
        data = self.read_json(".llm-wiki/settings.json", {})
        defaults = {
            "language": "zh",
            "autoIngest": True,
            "vectorSearch": True,
            "contextTokens": 32000,
            "historyDepth": 10,
            "reviewPolicy": "balanced",
            "template": resolve_template(None).id,
        }
        if isinstance(data, dict):
            defaults.update({key: value for key, value in data.items() if value is not None})
        return defaults

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.settings()
            current.update({key: value for key, value in patch.items() if value is not None})
            self.write_json(".llm-wiki/settings.json", current)
            return current

    # ------------------------------------------------------------------
    # 删除级联
    # ------------------------------------------------------------------
    def delete_source(self, relative: str) -> dict[str, Any]:
        """删除来源并级联清理：来源摘要页、其他页 sources 引用、index/log/overview。"""
        target = self.path(relative)
        if not target.is_file():
            raise FileNotFoundError(relative)
        name = target.name
        stem = target.stem
        target.unlink()
        self.drop_ingest_cache(name)

        removed_pages: list[str] = []
        touched_pages: list[str] = []
        summary_relative = f"wiki/sources/{stem}.md"
        if self.path(summary_relative).is_file():
            self.path(summary_relative).unlink()
            removed_pages.append(summary_relative)

        for record in self.page_records():
            if name not in record.sources and stem not in record.sources:
                continue
            remaining = [item for item in record.sources if item not in {name, stem}]
            if not remaining and record.type == "source":
                self.path(record.path).unlink()
                removed_pages.append(record.path)
                continue
            meta = dict(record.meta)
            meta["sources"] = remaining
            meta["updated"] = today()
            self.write_text(record.path, build_frontmatter(meta) + "\n" + normalize_body(record.body))
            touched_pages.append(record.path)

        self.rebuild_index()
        self.rebuild_overview()
        self.append_log("delete", name, f"移除 {len(removed_pages)} 页 · 更新 {len(touched_pages)} 页")
        return {"removedPages": removed_pages, "touchedPages": touched_pages}

    def clear_pages(self) -> None:
        for path in self.wiki_dir.rglob("*.md"):
            if path.name in {"index.md", "log.md", "overview.md"}:
                continue
            path.unlink(missing_ok=True)
        self.write_json(".llm-wiki/ingest-cache.json", {"entries": {}})
        self.rebuild_index()
        self.rebuild_overview()

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        records = [record for record in self.page_records(include_body=False) if record.path not in SYSTEM_PAGES]
        return {
            "sources": len(self.source_files()),
            "pages": len(records),
            "reviews": len([item for item in self.reviews() if not item.get("resolved")]),
        }


def sanitize_project_id(project_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", project_id).strip(".-")
    return cleaned or "default"


def workspace_for(settings: Settings, project_id: str, project_name: str = "") -> WikiWorkspace:
    root = settings.data_path / "wiki" / sanitize_project_id(project_id)
    return WikiWorkspace(root, project_id, project_name)


def copy_source_file(workspace: WikiWorkspace, source: Path, filename: str | None = None) -> str:
    """把原始文件放入 raw/sources，重名时自动加序号，返回相对路径。"""
    name = (filename or source.name).strip() or source.name
    destination = workspace.sources_dir / name
    if destination.exists() and destination.resolve() != source.resolve():
        stem, suffix = destination.stem, destination.suffix
        index = 2
        while destination.exists():
            destination = workspace.sources_dir / f"{stem}-{index}{suffix}"
            index += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return destination.relative_to(workspace.root).as_posix()
