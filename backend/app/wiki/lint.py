"""质检（lint）：结构一致性与可维护性检查。

原则：错误 = 会让溯源或导航失效的问题；警告 = 影响知识质量但可后补的问题。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .graph import build_graph
from .store import SYSTEM_PAGES, PageRecord, WikiWorkspace, extract_links

SKIP = {"index", "log", "overview"}

_TYPE_DIR = {
    "entity": "entities",
    "concept": "concepts",
    "source": "sources",
    "query": "queries",
    "comparison": "comparisons",
    "synthesis": "synthesis",
    "thesis": "thesis",
    "finding": "findings",
    "methodology": "methodology",
    "decision": "decisions",
    "process": "processes",
    "metric": "metrics",
}


def run_lint(workspace: WikiWorkspace) -> dict[str, Any]:
    records = [record for record in workspace.page_records() if record.path not in SYSTEM_PAGES]
    issues: list[dict[str, str]] = []
    source_names = {path.name for path in workspace.source_files()}
    titles = {record.title for record in records}
    names = {record.name for record in records}
    index_text = workspace.read_text("wiki/index.md")
    graph = build_graph(workspace, records)

    for record in records:
        issues.extend(_check_page(record, source_names, titles, names, index_text, workspace))

    for record in records:
        if record.name in SKIP:
            continue
        if graph.degree(record.name) == 0:
            issues.append(_issue("warning", "orphan-page", record.path, "孤立页面：没有任何页面链接到它或由它链出"))

    size = len(records)
    errors = sum(1 for issue in issues if issue["level"] == "error")
    warnings = len(issues) - errors
    return {
        "issues": issues,
        "stats": {
            "pages": size,
            "errors": errors,
            "warnings": warnings,
            "health": round(max(0.0, 1 - (errors * 0.06 + warnings * 0.01)), 3),
            "links": sum(len(value) for value in graph.links.values()),
        },
    }


def _check_page(
    record: PageRecord,
    source_names: set[str],
    titles: set[str],
    names: set[str],
    index_text: str,
    workspace: WikiWorkspace,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not record.has_frontmatter:
        issues.append(_issue("error", "missing-frontmatter", record.path, "页面缺少 YAML frontmatter，溯源信息不可用"))
    if not record.meta.get("title"):
        issues.append(_issue("warning", "missing-title", record.path, "frontmatter 缺少 title"))
    if not record.type:
        issues.append(_issue("warning", "missing-type", record.path, "frontmatter 缺少 type"))
    elif record.type in _TYPE_DIR and record.dir != _TYPE_DIR[record.type] and record.dir not in {"wiki", ""}:
        issues.append(
            _issue(
                "warning",
                "type-dir-mismatch",
                record.path,
                f"类型 {record.type} 通常应放在 wiki/{_TYPE_DIR[record.type]}/，当前在 {record.dir}/",
            )
        )
    if len(record.body.strip()) < 80:
        issues.append(_issue("warning", "thin-page", record.path, "正文过短（<80 字），可能是空壳页"))

    for source in record.sources:
        if source.startswith(("web:", "http://", "https://")):
            # 网络研究来源以域名记录，不对应 raw/sources 下的文件
            continue
        if Path(source).name in source_names:
            continue
        issues.append(_issue("error", "missing-source", record.path, f"引用的原始资料不存在：{source}"))
    for link in extract_links(record.body):
        if link not in titles and link not in names and link.replace(".md", "") not in names:
            issues.append(_issue("warning", "broken-wikilink", record.path, f"[[{link}]] 指向不存在的页面"))

    if record.name not in SKIP and record.title not in index_text:
        issues.append(_issue("warning", "not-in-index", record.path, "index.md 未收录该页面"))

    created, updated = record.created, record.updated
    if created and updated and created > updated:
        issues.append(_issue("warning", "date-order", record.path, f"updated（{updated}）早于 created（{created}）"))
    if not record.sources and record.type not in {"overview"}:
        issues.append(_issue("warning", "missing-sources", record.path, "页面没有记录任何来源，结论无法溯源"))

    body = workspace.read_text(record.path)
    if "TODO" in body or "待补充" in body:
        issues.append(_issue("info", "needs-fill", record.path, "页面仍含待补充占位内容"))
    return issues


def _issue(level: str, code: str, file: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "file": file, "message": message}


def lint_labels() -> dict[str, str]:
    return {
        "missing-frontmatter": "frontmatter 缺失",
        "missing-title": "标题缺失",
        "missing-type": "类型缺失",
        "type-dir-mismatch": "类型与目录不一致",
        "thin-page": "内容过薄",
        "missing-source": "来源缺失",
        "missing-sources": "未记录来源",
        "broken-wikilink": "断链",
        "orphan-page": "孤立页面",
        "not-in-index": "索引未收录",
        "date-order": "日期顺序异常",
        "needs-fill": "待补充",
    }
