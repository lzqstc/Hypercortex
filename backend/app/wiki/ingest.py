"""摄取（ingest）：把原始资料编译成结构化 wiki 页面。

两步式思维链：
    Step 1 分析 —— 抽取实体、概念、主张、证据、矛盾、结构建议
    Step 2 生成 —— 产出带 frontmatter 的 wiki 文件与待审阅项

工程要点：
- SHA256 增量缓存：内容未变的来源直接跳过
- 长文档分片：按标题切分 + 重叠窗口 + 全局摘要滚动合并，避免超窗
- 持久化队列：串行处理、失败可重试、可取消、进度可观测
- 无 LLM 时走确定性编译降级路径，保证功能可用
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ..config import Settings
from ..services.embeddings import EmbeddingService
from ..services.parsers import ParserError, parse_file
from .llm import LLMBridge, LLMUnavailable
from .store import (
    PageRecord,
    WikiWorkspace,
    build_frontmatter,
    normalize_body,
    parse_frontmatter,
    safe_slug,
    sha256_text,
    today,
    utcnow,
)
from .templates import resolve_template
from .vectors import PageVectorIndex

logger = logging.getLogger(__name__)

FILE_BLOCK_RE = re.compile(r"---\s*FILE:\s*(.+?)\s*---\r?\n(.*?)\r?\n---\s*END FILE\s*---", re.S)
REVIEW_BLOCK_RE = re.compile(r"---\s*REVIEW:\s*(.+?)\s*---\r?\n(.*?)\r?\n---\s*END REVIEW\s*---", re.S)
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.M)

MAX_SINGLE_PASS_CHARS = 24000
MAX_SOURCE_PROMPT_CHARS = 60000
CHUNK_TARGET = 9000
CHUNK_OVERLAP = 900
MAX_PAGES_PER_INGEST = 24

_LEAD_STOP = {
    "本文", "本文档", "本报告", "报告", "前言", "摘要", "目录", "附录", "结论", "参考文献",
    "introduction", "conclusion", "summary", "overview", "index", "contents",
}

try:  # pragma: no cover - 可选依赖
    import jieba  # type: ignore
    import jieba.analyse  # type: ignore

    jieba.setLogLevel(60)
    _HAS_JIEBA = True
except Exception:  # noqa: BLE001
    _HAS_JIEBA = False


# ---------------------------------------------------------------------------
# 任务模型
# ---------------------------------------------------------------------------


@dataclass
class IngestTask:
    id: str
    project_id: str
    source_path: str
    source_name: str
    status: str = "queued"
    stage: str = "排队中"
    detail: str = ""
    attempts: int = 0
    error: str = ""
    pages_written: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    force: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "sourcePath": self.source_path,
            "sourceName": self.source_name,
            "status": self.status,
            "stage": self.stage,
            "detail": self.detail,
            "attempts": self.attempts,
            "error": self.error,
            "pagesWritten": self.pages_written,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestTask":
        return cls(
            id=str(data.get("id") or f"task_{uuid.uuid4().hex[:10]}"),
            project_id=str(data.get("projectId") or data.get("project_id") or ""),
            source_path=str(data.get("sourcePath") or data.get("source_path") or ""),
            source_name=str(data.get("sourceName") or data.get("source_name") or ""),
            status=str(data.get("status") or "queued"),
            stage=str(data.get("stage") or ""),
            detail=str(data.get("detail") or ""),
            attempts=int(data.get("attempts") or 0),
            error=str(data.get("error") or ""),
            pages_written=list(data.get("pagesWritten") or []),
            created_at=str(data.get("createdAt") or utcnow()),
            updated_at=str(data.get("updatedAt") or utcnow()),
            force=bool(data.get("force")),
        )


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM = """你在为个人研究型 wiki 分析一份原始资料。
不要输出思维链、内心独白或推理过程，只输出要求的两个小节。

## 片段分析
- 一句话概括本片段
- 新出现或需要更新的实体（具名事物：人物、组织、产品、系统、数据集）
- 新出现或需要更新的概念（方法、技术、框架、指标、现象）
- 本片段真正支撑的其他页面类型（按 schema 定义，不发明类型）
- 主张、发现、证据、矛盾；每条注明来自哪一段
- 本片段中的结构化数据（表格、DDL、API 签名、参数配置）必须原样保留
- 尚未回答的问题或证据缺口

## 更新后的全局摘要
在保留上文跨片段上下文的前提下，滚动更新为一份文档级摘要，固定结构：
摘要 / 实体 / 概念 / 候选页面类型 / 主张 / 证据 / 矛盾 / 开放问题 / 跨片段关系

规则：
- 只写原文支持的内容，不补充外部知识
- 数字、口径、时间范围、单位必须与原文一致
- 实体与概念的命名保持稳定，与已有 wiki 索引一致
"""


def build_analysis_prompt(workspace: WikiWorkspace, source_name: str, digest: str, chunk: str, part: str = "") -> str:
    parts = [
        f"来源文件：{source_name}",
        f"日期：{today()}",
        "",
        "## Wiki 意图（purpose.md）",
        workspace.purpose()[:4000] or "（未填写）",
        "",
        "## Wiki 规则（schema.md）",
        workspace.schema()[:6000] or "（未填写）",
        "",
        "## 当前索引（节选）",
        workspace.read_text("wiki/index.md")[:12000] or "（空）",
    ]
    if digest:
        parts.extend(["", "## 已有全局摘要", digest[:6000]])
    if part:
        parts.extend(["", f"## 当前处理范围", part])
    parts.extend(["", "## 待分析原文", chunk[:MAX_SOURCE_PROMPT_CHARS], "", "只输出「片段分析」与「更新后的全局摘要」两个小节。"])
    return "\n".join(parts)


GENERATION_RULES = """## 必须生成的内容

1. 一个来源摘要页，路径必须精确为 **{summary_path}**，frontmatter 的 `sources` 必须包含 `{source_name}`
2. 关键具名事物的实体页（优先使用 schema 定义的目录，否则 wiki/entities/）
3. 关键概念/方法/指标的概念页（优先 schema 目录，否则 wiki/concepts/）
4. 如确有需要，生成 schema 允许的其他类型页（问题、对比、综合、论点、发现、方法等）
5. 一条日志条目（仅条目文本，格式：`- ingest | {source_name} | 新建 N 页`）

禁止生成 wiki/index.md、wiki/overview.md、wiki/log.md 整页 —— 这些由系统维护。

## Frontmatter 规则（解析器严格）

- 文件第一行必须是 `---`，不要用 ```yaml 代码块包裹
- 字段：type / title / tags / related / sources / created / updated
- `type` 必须与所在目录对应；`related` 只写裸 slug；wikilink 只写在正文
- 新建页面 `created` 与 `updated` 都写 `{today}`
- 示例：
    ---
    type: concept
    title: 需求价格弹性
    tags: [定价, 经济学]
    related: [定价分层, 价格敏感度]
    sources: ["{source_name}"]
    created: {today}
    updated: {today}
    ---

## 内容规则

- 正文使用简体中文；专有名词、模型名、数据集名、库名、代码标识符保留原文
- 正文用 `[[页面标题]]` 建立交叉引用
- 每条关键结论后注明依据（原文段落、页码或来源文件名）
- 保持主体边界：不同对象的主张不得混写；需要对比时明确写「对比」
- 结构化数据（表格、DDL、参数）原样放进代码块或 Markdown 表格，不要改写
- 文件名：拉丁文用 kebab-case；中文标题保留中文字符
- 宁少勿滥：不确定是否值得单独成页的，写成摘要页里的小节并在审阅项里提出

## 待审阅项（可选，放在全部 FILE 块之后）

- contradiction：与已有 wiki 内容冲突
- duplicate：可能与已有页面重名
- missing-page：被引用但缺少独立页面
- suggestion：值得进一步研究的方向

OPTIONS 只允许 `Create Page | Skip`；missing-page / suggestion 需给出 2-3 条检索式。

## 输出格式（必须严格遵守）

```
---FILE: wiki/concepts/示例.md---
（完整文件内容，含 frontmatter）
---END FILE---

---REVIEW: missing-page | 待建页面标题---
说明
OPTIONS: Create Page | Skip
PAGES: wiki/concepts/已有页面.md
SEARCH: 检索式1 | 检索式2
---END REVIEW---
```

- 第一个字符必须是 `-`（`---FILE:` 的开头），不得有任何前言、解释、后续评论
- 不得在 FILE/REVIEW 块之外输出任何 markdown 内容
"""


def build_generation_prompt(
    workspace: WikiWorkspace,
    source_name: str,
    analysis: str,
    overview: str,
) -> str:
    summary_path = f"wiki/sources/{safe_slug(Path(source_name).stem)}.md"
    rules = GENERATION_RULES.format(summary_path=summary_path, source_name=source_name, today=today())
    return "\n".join(
        [
            "你是 wiki 维护者。根据下面的分析和项目规则，生成 wiki 文件。",
            "不要输出思维链或解释性前言，只输出 FILE / REVIEW 块。",
            "",
            "## 项目规则（schema.md，权威）",
            workspace.schema()[:8000] or "（未填写）",
            "",
            "## 项目意图（purpose.md）",
            workspace.purpose()[:4000] or "（未填写）",
            "",
            "## 当前索引（保留已有条目，仅新增）",
            workspace.read_text("wiki/index.md")[:16000] or "（空）",
            "",
            "## 当前总览",
            overview[:4000] or "（空）",
            "",
            rules,
            "",
            "## 来源",
            f"原始文件名：{source_name}",
            "",
            "## Step 1 分析结果",
            analysis[:20000],
            "",
            "现在开始输出 FILE 块。",
        ]
    )


# ---------------------------------------------------------------------------
# 解析与工具
# ---------------------------------------------------------------------------


def parse_file_blocks(raw: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for match in FILE_BLOCK_RE.finditer(raw or ""):
        path = match.group(1).strip().strip("`").replace("\\", "/")
        content = match.group(2)
        if not path:
            continue
        blocks.append({"path": path, "content": content})
    return blocks


def parse_review_blocks(raw: str) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for match in REVIEW_BLOCK_RE.finditer(raw or ""):
        header = match.group(1).strip()
        body = match.group(2).strip()
        review_type, _, title = header.partition("|")
        messages: dict[str, str] = {}
        description_lines: list[str] = []
        for line in body.splitlines():
            upper = line.upper()
            if upper.startswith("OPTIONS:"):
                messages["options"] = line.split(":", 1)[1].strip()
            elif upper.startswith("PAGES:"):
                messages["pages"] = line.split(":", 1)[1].strip()
            elif upper.startswith("SEARCH:"):
                messages["search"] = line.split(":", 1)[1].strip()
            elif line.strip():
                description_lines.append(line.strip())
        reviews.append(
            {
                "type": review_type.strip() or "suggestion",
                "title": title.strip() or "未命名审阅项",
                "description": " ".join(description_lines)[:800],
                "affectedPages": [item.strip() for item in (messages.get("pages") or "").split(",") if item.strip()],
                "searchQueries": [item.strip() for item in (messages.get("search") or "").split("|") if item.strip()],
                "options": _normalize_options(messages.get("options") or ""),
            }
        )
    return reviews


def _normalize_options(raw: str) -> list[dict[str, str]]:
    labels = [item.strip() for item in raw.split("|") if item.strip()]
    allowed = {"Create Page": "建立页面", "Skip": "跳过"}
    options: list[dict[str, str]] = []
    for label in labels:
        for canonical, chinese in allowed.items():
            if label.lower() == canonical.lower() or label == chinese:
                options.append({"label": chinese, "action": canonical})
    if not options:
        options = [{"label": "建立页面", "action": "Create Page"}, {"label": "跳过", "action": "Skip"}]
    return options


def split_long_source(text: str, target: int = CHUNK_TARGET, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """优先按标题切分，保证不把一个小节劈成两半。"""
    if len(text) <= target * 1.2:
        return [text]
    blocks: list[str] = []
    cursor = 0
    current: list[str] = []
    current_len = 0
    for match in HEADING_RE.finditer(text):
        start = match.start()
        if start > cursor:
            piece = text[cursor:start]
            current.append(piece)
            current_len += len(piece)
        if current_len >= target and current:
            blocks.append("".join(current))
            tail = "".join(current)[-overlap:]
            current = [tail]
            current_len = len(tail)
        heading_start = start
        cursor = heading_start
    tail = text[cursor:]
    if tail:
        current.append(tail)
        current_len += len(tail)
    if current:
        blocks.append("".join(current))
    if not blocks:
        blocks = [text[index : index + target] for index in range(0, len(text), target - overlap)]
    return [block for block in blocks if block.strip()]


def document_payload(workspace: WikiWorkspace, relative: str, settings: Settings) -> tuple[str, str]:
    """读取来源正文。文本类直接读，其他格式复用已有解析器。"""
    path = workspace.path(relative)
    name = path.name
    text_exts = {".md", ".markdown", ".txt", ".csv", ".json", ".html", ".htm"}
    if path.suffix.lower() in text_exts:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return raw, name
        try:
            sections = parse_file(path, name, settings.ocr_enabled)
        except ParserError:
            return raw, name
    else:
        sections = parse_file(path, name, settings.ocr_enabled)
    lines: list[str] = []
    for section in sections:
        heading = section.section.strip()
        if heading:
            lines.append(f"## {heading}")
        if section.page:
            lines.append(f"<!-- page {section.page} -->")
        lines.append(section.text.strip())
        lines.append("")
    return "\n".join(lines).strip(), name


GENERIC_TERMS = {
    "瓶颈", "现状", "结论", "背景", "分析", "问题", "影响", "作用", "趋势", "观点", "数据",
    "研究", "报告", "本文", "摘要", "核心", "要点", "方面", "情况", "内容", "方法", "结果",
    "发展", "建设", "管理", "存在", "具有", "进行", "通过", "以及", "同时", "因此", "但是",
}


def _clean_for_keywords(text: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    cleaned = re.sub(r"[*_>`\[\]|]", " ", cleaned)
    return cleaned


_NOUN_FLAGS = {"n", "nz", "vn", "nt", "ns", "an", "nw"}
_TERM_SHAPE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9\-]+$")


def _noun_pool(text: str) -> tuple[Counter, Counter]:
    """返回（单词名词池, 相邻名词拼接池）。

    分词器常把专有术语切碎（「低空」+「经济」），单靠词频会得到碎片而不是
    完整术语。这里额外统计**连续名词拼接**，让「低空经济」这类复合词以更高
    分值进入候选，后面的「包含关系去碎片」才能把「低空」吸收掉。
    """
    singles: Counter = Counter()
    merges: Counter = Counter()
    try:
        import jieba.posseg as pseg
    except Exception:  # noqa: BLE001
        return singles, merges
    previous = ""
    try:
        for word, flag in pseg.cut(text[:120000]):
            token = word.strip()
            usable = len(token) >= 2 and "的" not in token and flag in _NOUN_FLAGS and bool(_TERM_SHAPE.match(token))
            if usable:
                singles[token] += 1
                if previous and len(previous) + len(token) <= 8:
                    merges[previous + token] += 1
            previous = token if usable else ""
    except Exception:  # noqa: BLE001
        return singles, merges
    return singles, merges


def _keywords(text: str, limit: int = 24) -> list[str]:
    cleaned = _clean_for_keywords(text)
    scored: dict[str, float] = {}
    if _HAS_JIEBA:
        try:
            for tag in jieba.analyse.extract_tags(cleaned, topK=limit * 4, withWeight=True):
                term, weight = tag
                term = str(term).strip()
                if len(term) >= 2:
                    scored[term] = max(scored.get(term, 0.0), float(weight) * 10)
        except Exception:  # noqa: BLE001
            pass
        singles, merges = _noun_pool(cleaned)
        for term, count in merges.items():
            # 复合术语必须重复出现，避免把一次性的「A的B」拼成假术语
            if count >= 2:
                scored[term] = max(scored.get(term, 0.0), count * (1 + 0.25 * len(term)))
        for term, count in singles.items():
            # 专有名词按「频次 × 长度」加权：长术语的信息量更高
            scored[term] = max(scored.get(term, 0.0), count * (1 + 0.25 * len(term)))

    if not scored:
        counter: Counter = Counter()
        for run in re.findall(r"[\u4e00-\u9fff]{2,8}", cleaned):
            for size in (2, 3, 4):
                for index in range(0, len(run) - size + 1):
                    counter[run[index : index + size]] += 1
        for word in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", cleaned):
            counter[word] += 2
        scored = {item: float(count) for item, count in counter.items() if count >= 2}

    def valid(term: str) -> bool:
        stripped = term.strip()
        if len(stripped) < 2 or stripped in GENERIC_TERMS:
            return False
        if re.fullmatch(r"[\W\d_]+", stripped):
            return False
        if any(mark in stripped for mark in "#*`[]|<>"):
            return False
        return True

    ordered = [term for term, _ in sorted(scored.items(), key=lambda item: (-item[1], -len(item[0])))]
    ordered = [term for term in ordered if valid(term)]
    # 去掉被更长候选完全包含的碎片（例如「低空」被「低空经济」吸收）
    survivors = [
        term
        for term in ordered
        if not any(term != other and term in other and len(other) > len(term) for other in ordered)
    ]
    return survivors[:limit]


_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;\n])")


def _sentences(text: str) -> list[str]:
    items = [re.sub(r"\s+", " ", part).strip() for part in _SENT_SPLIT.split(text)]
    return [item for item in items if 18 <= len(item) <= 320 and not item.startswith("#")]


def _score_sentences(text: str, keywords: Iterable[str], limit: int = 8) -> list[str]:
    keyword_set = {item.lower() for item in keywords}
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(_sentences(text)):
        lowered = sentence.lower()
        hits = sum(1 for keyword in keyword_set if keyword and keyword in lowered)
        if not hits:
            continue
        digits = 1.2 if re.search(r"\d", sentence) else 0.0
        scored.append((hits + digits, -index, sentence))
    scored.sort(reverse=True)
    picked: list[str] = []
    seen: set[str] = set()
    for _, _, sentence in scored:
        key = re.sub(r"\W+", "", sentence)[:40]
        if key in seen:
            continue
        seen.add(key)
        picked.append(sentence)
        if len(picked) >= limit:
            break
    return picked


def _extract_heading_map(text: str) -> list[tuple[str, int]]:
    headings: list[tuple[str, int]] = []
    for match in HEADING_RE.finditer(text):
        title = match.group(2).strip()
        if title and title.lower() not in _LEAD_STOP:
            headings.append((title, len(match.group(1))))
    return headings


def _guess_entities(text: str, limit: int = 6) -> list[str]:
    counter: Counter = Counter()
    for match in re.findall(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})\b", text):
        if len(match) > 2:
            counter[match] += 1
    for match in re.findall(r"《([^》]{2,24})》", text):
        counter[match] += 3
    stop = {"The", "This", "That", "Figure", "Table", "Section", "Chapter", "However"}
    return [item for item, count in counter.most_common(limit * 3) if item not in stop and count >= 2][:limit]


def _quote(text: str, limit: int = 3) -> list[str]:
    quotes = [item for item in _sentences(text) if len(item) >= 30]
    return quotes[:limit]


def heuristic_compile(
    workspace: WikiWorkspace,
    source_name: str,
    text: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
    """无 LLM 时的确定性编译：结构化摘要 + 高频概念页 + 具名实体页。"""
    keywords = _keywords(text, 22)
    highlights = _score_sentences(text, keywords, 9)
    headings = _extract_heading_map(text)
    entities = _guess_entities(text, 4)
    concept_terms = [item for item in keywords if item not in entities][:6]
    summary_slug = safe_slug(Path(source_name).stem)
    summary_title = Path(source_name).stem
    chars = len(text)
    # 导语优先取正文第一句，而不是相似度最高的一句（后者常是数据句）
    first_sentence = next((item for item in _sentences(text) if len(item) >= 24), "")
    lead = [first_sentence] if first_sentence else highlights[:1]
    bullets = [item for item in highlights if item != first_sentence][:7]
    section_list = [f"- {title}" for title, _ in headings[:14] if title != summary_title] or ["- （原文未使用标题层级）"]

    def link(term: str) -> str:
        return f"[[{term}]]" if len(term) >= 2 else term

    body_lines = [
        f"# {summary_title}",
        "",
        f"> 来源：`{source_name}` · 约 {chars} 字 · {len(headings)} 个章节 · 编译于 {today()}",
        "",
        "## 一句话概括",
        "",
        lead[0] if lead else "（原文缺少可提取的完整句子，建议人工补充摘要）",
        "",
        "## 核心要点",
        "",
    ]
    for sentence in bullets or lead:
        body_lines.append(f"- {sentence}")
    body_lines.extend(["", "## 结构", ""] + section_list)
    if concept_terms:
        body_lines.extend(["", "## 关键概念", ""])
        for term in concept_terms[:6]:
            body_lines.append(f"- {link(term)}")
    if entities:
        body_lines.extend(["", "## 涉及的具名事物", ""])
        for name in entities:
            body_lines.append(f"- {link(name)}")
    quotes = _quote(text, 3)
    if quotes:
        body_lines.extend(["", "## 原文摘录（可溯源）", ""])
        for sentence in quotes:
            body_lines.append(f"> {sentence}")
            body_lines.append("")
    body_lines.extend(
        [
            "",
            "## 编译说明",
            "",
            "- 本页由确定性抽取生成（未配置 LLM 时的降级路径）：要点按关键词密度与包含数字的句子加权排序。",
            "- 配置 LLM 后重新编译可获得实体识别、矛盾检测、跨来源综合等能力。",
            "",
        ]
    )

    files: list[dict[str, str]] = [
        {
            "path": f"wiki/sources/{summary_slug}.md",
            "content": build_frontmatter(
                {
                    "type": "source",
                    "title": summary_title,
                    "tags": keywords[:5],
                    "related": concept_terms[:4],
                    "sources": [source_name],
                    "created": today(),
                    "updated": today(),
                }
            )
            + "\n"
            + "\n".join(body_lines),
        }
    ]

    for term in concept_terms[:5]:
        context = next((item for item in _sentences(text) if term in item), "")
        files.append(
            {
                "path": f"wiki/concepts/{safe_slug(term)}.md",
                "content": build_frontmatter(
                    {
                        "type": "concept",
                        "title": term,
                        "tags": keywords[:4],
                        "related": [summary_title],
                        "sources": [source_name],
                        "created": today(),
                        "updated": today(),
                    }
                )
                + "\n"
                + "\n".join(
                    [
                        f"# {term}",
                        "",
                        "## 在资料中的含义",
                        "",
                        context or f"该术语在《{summary_title}》中反复出现，尚未抽取到完整定义句。",
                        "",
                        "## 关联",
                        "",
                        f"- 来源摘要：[[{summary_title}]]",
                        "",
                        "## 待补充",
                        "",
                        "- 定义、边界条件、与相邻概念的差异",
                        "",
                    ]
                ),
            }
        )

    for name in entities[:3]:
        context = next((item for item in _sentences(text) if name in item), "")
        files.append(
            {
                "path": f"wiki/entities/{safe_slug(name)}.md",
                "content": build_frontmatter(
                    {
                        "type": "entity",
                        "title": name,
                        "tags": ["实体"],
                        "related": [summary_title],
                        "sources": [source_name],
                        "created": today(),
                        "updated": today(),
                    }
                )
                + "\n"
                + "\n".join(
                    [
                        f"# {name}",
                        "",
                        "## 资料中的描述",
                        "",
                        context or f"《{summary_title}》提及该主体，但未给出完整描述。",
                        "",
                        "## 关联",
                        "",
                        f"- 来源摘要：[[{summary_title}]]",
                        "",
                    ]
                ),
            }
        )

    reviews = [
        {
            "type": "suggestion",
            "title": f"补全《{summary_title}》的关键概念定义",
            "description": "确定性编译只抽取了术语出现的句子，没有形成定义。建议补充资料或配置 LLM 后重新编译。",
            "affectedPages": [f"wiki/sources/{summary_slug}.md"],
            "searchQueries": [f"{summary_title} 核心概念 定义", f"{' '.join(concept_terms[:2])} 综述"],
            "options": [{"label": "建立页面", "action": "Create Page"}, {"label": "跳过", "action": "Skip"}],
        }
    ]
    analysis = "\n".join(
        [
            "## 片段分析（确定性抽取）",
            f"- 关键词：{'、'.join(keywords[:12])}",
            f"- 章节：{'、'.join(title for title, _ in headings[:10]) or '无'}",
            f"- 具名事物：{'、'.join(entities) or '未识别'}",
            "",
            "## 更新后的全局摘要",
            lead[0] if lead else "",
        ]
    )
    return files, reviews, analysis


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------


class IngestService:
    def __init__(self, settings: Settings, embeddings: EmbeddingService):
        self.settings = settings
        self.embeddings = embeddings
        self.llm = LLMBridge(settings)
        self._workspaces: dict[str, WikiWorkspace] = {}
        self._worker: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._inflight: set[str] = set()
        self._lock = threading.RLock()

    # -- 生命周期 ------------------------------------------------------
    def register(self, workspace: WikiWorkspace) -> None:
        with self._lock:
            self._workspaces[workspace.project_id] = workspace

    async def start(self) -> None:
        if self._worker and not self._worker.done():
            return
        self._stop.clear()
        self._worker = asyncio.create_task(self._run(), name="wiki-ingest-worker")
        logger.info("Wiki ingest worker started")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._worker = None
        logger.info("Wiki ingest worker stopped")

    def wake(self) -> None:
        self._wake.set()

    # -- 队列 ----------------------------------------------------------
    def queue(self, project_id: str) -> list[dict[str, Any]]:
        workspace = self._workspaces.get(project_id)
        if not workspace:
            return []
        return workspace.queue()

    def enqueue(self, workspace: WikiWorkspace, source_paths: list[str], *, force: bool = False) -> list[dict[str, Any]]:
        self.register(workspace)
        workspace.ensure()
        existing = workspace.queue()
        created: list[dict[str, Any]] = []
        for relative in source_paths:
            name = Path(relative).name
            duplicate = next(
                (
                    item
                    for item in existing
                    if item.get("sourcePath") == relative
                    and item.get("status") in {"queued", "running"}
                ),
                None,
            )
            if duplicate:
                created.append(duplicate)
                continue
            task = IngestTask(
                id=f"task_{uuid.uuid4().hex[:10]}",
                project_id=workspace.project_id,
                source_path=relative,
                source_name=name,
                force=force,
            )
            payload = task.as_dict()
            payload["force"] = force
            existing.append(payload)
            created.append(payload)
        workspace.save_queue(existing)
        self.wake()
        return created

    def cancel(self, project_id: str, task_id: str) -> bool:
        workspace = self._workspaces.get(project_id)
        if not workspace:
            return False
        queue = workspace.queue()
        changed = False
        for item in queue:
            if item.get("id") == task_id and item.get("status") in {"queued", "running"}:
                item["status"] = "cancelled"
                item["stage"] = "已取消"
                item["updatedAt"] = utcnow()
                changed = True
        if changed:
            workspace.save_queue(queue)
        return changed

    def retry(self, project_id: str, task_id: str) -> bool:
        workspace = self._workspaces.get(project_id)
        if not workspace:
            return False
        queue = workspace.queue()
        changed = False
        for item in queue:
            if item.get("id") == task_id and item.get("status") in {"error", "cancelled"}:
                item["status"] = "queued"
                item["stage"] = "重新排队"
                item["error"] = ""
                item["updatedAt"] = utcnow()
                changed = True
        if changed:
            workspace.save_queue(queue)
            self.wake()
        return changed

    def _patch(self, workspace: WikiWorkspace, task_id: str, **fields: Any) -> None:
        with self._lock:
            queue = workspace.queue()
            for item in queue:
                if item.get("id") == task_id:
                    item.update(fields)
                    item["updatedAt"] = utcnow()
                    break
            workspace.save_queue(queue)

    # -- worker --------------------------------------------------------
    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                task_ref = self._next_task()
            except Exception:  # noqa: BLE001
                logger.exception("Wiki ingest: failed to inspect queues")
                task_ref = None
            if not task_ref:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                continue
            workspace, task = task_ref
            try:
                await asyncio.to_thread(self._process, workspace, task)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Wiki ingest failed: %s", task.get("sourceName"))
                self._patch(
                    workspace,
                    str(task.get("id")),
                    status="error",
                    stage="失败",
                    error=str(exc)[:400],
                    attempts=int(task.get("attempts") or 0) + 1,
                )

    def _next_task(self) -> tuple[WikiWorkspace, dict[str, Any]] | None:
        with self._lock:
            for workspace in list(self._workspaces.values()):
                if not workspace.exists():
                    continue
                for item in workspace.queue():
                    if item.get("status") == "queued":
                        return workspace, item
        return None

    # -- 单个任务 ------------------------------------------------------
    def _process(self, workspace: WikiWorkspace, task: dict[str, Any]) -> None:
        task_id = str(task.get("id"))
        relative = str(task.get("sourcePath") or "")
        source_name = str(task.get("sourceName") or Path(relative).name)
        self._patch(workspace, task_id, status="running", stage="读取资料", detail=source_name, error="")
        try:
            text, name = document_payload(workspace, relative, self.settings)
        except (OSError, ParserError) as exc:
            self._patch(workspace, task_id, status="error", stage="解析失败", error=str(exc)[:300])
            return
        if not text.strip():
            self._patch(workspace, task_id, status="error", stage="空文档", error="解析后没有可用文本（可能是扫描件）")
            return

        digest = sha256_text(text)
        cache = workspace.ingest_cache()["entries"].get(source_name) or {}
        if cache.get("hash") == digest and not task.get("force"):
            self._patch(
                workspace,
                task_id,
                status="done",
                stage="已跳过",
                detail="内容未变化，命中增量缓存",
                pagesWritten=list(cache.get("filesWritten") or []),
            )
            return

        settings = workspace.settings()
        self._patch(workspace, task_id, stage="分析内容", detail=f"{len(text)} 字")
        try:
            if self.llm.available():
                files, reviews, analysis = self._compile_with_llm(workspace, source_name, text, task_id)
            else:
                files, reviews, analysis = heuristic_compile(workspace, source_name, text)
                self._patch(workspace, task_id, detail="未配置 LLM，使用确定性编译")
        except LLMUnavailable:
            files, reviews, analysis = heuristic_compile(workspace, source_name, text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM compile failed, falling back to heuristic: %s", exc)
            files, reviews, analysis = heuristic_compile(workspace, source_name, text)

        self._patch(workspace, task_id, stage="写入页面", detail=f"{len(files)} 个文件")
        written = self._commit(workspace, source_name, files)
        workspace.add_reviews(reviews)
        workspace.rebuild_index()
        workspace.rebuild_overview()
        workspace.append_log("ingest", source_name, f"新建/更新 {len(written)} 页 · 审阅 {len(reviews)} 项")
        workspace.update_ingest_cache(
            source_name,
            {
                "hash": digest,
                "filesWritten": written,
                "ingestedAt": utcnow(),
                "analysis": analysis[:4000],
            },
        )
        if settings.get("vectorSearch", True):
            # 向量索引是可选增强：模型缺失或不可用时只跳过索引，不能让编译失败
            try:
                index = PageVectorIndex(workspace, self.embeddings)
                for relative_page in written:
                    try:
                        record = workspace.page_record(relative_page)
                        index.upsert(record.path, f"{record.title}\n{record.body}")
                    except (OSError, FileNotFoundError):
                        continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vector index skipped for %s: %s", source_name, exc)
        self._patch(
            workspace,
            task_id,
            status="done",
            stage="已完成",
            detail=f"编译 {len(written)} 页",
            pagesWritten=written,
            attempts=int(task.get("attempts") or 0) + 1,
        )

    # -- LLM 两步编译 --------------------------------------------------
    def _compile_with_llm(
        self,
        workspace: WikiWorkspace,
        source_name: str,
        text: str,
        task_id: str,
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
        chunks = split_long_source(text) if len(text) > MAX_SINGLE_PASS_CHARS else [text]
        digest = ""
        analyses: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            self._patch(
                workspace,
                task_id,
                stage="分析内容",
                detail=f"分片 {index}/{len(chunks)}",
            )
            prompt = build_analysis_prompt(
                workspace,
                source_name,
                digest,
                chunk,
                part=f"第 {index}/{len(chunks)} 片" if len(chunks) > 1 else "",
            )
            try:
                result = self.llm.chat(
                    [
                        {"role": "system", "content": ANALYSIS_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=3000,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Analysis chunk %s failed: %s", index, exc)
                result = ""
            if result:
                analyses.append(result)
                digest = _extract_section(result, "更新后的全局摘要") or digest or result[-2000:]

        analysis = "\n\n".join(analyses) if analyses else ""
        if not analysis:
            raise LLMUnavailable("LLM 分析未返回内容")

        self._patch(workspace, task_id, stage="生成页面", detail="Step 2 / 2")
        prompt = build_generation_prompt(workspace, source_name, analysis, workspace.read_text("wiki/overview.md"))
        raw = self.llm.chat(
            [
                {"role": "system", "content": "你是 wiki 维护者。只输出 FILE / REVIEW 块，不要任何前言或解释。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=8000,
            timeout=300,
        )
        files = parse_file_blocks(raw)
        reviews = parse_review_blocks(raw)
        if not files:
            logger.warning("Generation returned no FILE blocks; falling back to heuristic")
            heuristic_files, heuristic_reviews, heuristic_analysis = heuristic_compile(workspace, source_name, text)
            return heuristic_files, heuristic_reviews + reviews, analysis or heuristic_analysis
        return files, reviews, analysis

    # -- 落盘 ----------------------------------------------------------
    def _commit(self, workspace: WikiWorkspace, source_name: str, files: list[dict[str, str]]) -> list[str]:
        written: list[str] = []
        summary_expected = f"wiki/sources/{safe_slug(Path(source_name).stem)}.md"
        has_summary = False
        for block in files[:MAX_PAGES_PER_INGEST]:
            relative = _sanitize_wiki_path(block["path"])
            if not relative:
                continue
            content = block["content"].strip()
            if not content:
                continue
            meta, body = parse_frontmatter(content)
            page_type = str(meta.get("type") or _infer_type(relative))
            title = str(meta.get("title") or Path(relative).stem)
            if page_type in {"index", "log", "overview"} or Path(relative).name in {"index.md", "log.md", "overview.md"}:
                continue
            sources = meta.get("sources") if isinstance(meta.get("sources"), list) else []
            if page_type == "source" and source_name not in sources:
                sources = [*sources, source_name]
            tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
            related = meta.get("related") if isinstance(meta.get("related"), list) else []
            front = build_frontmatter(
                {
                    "type": page_type,
                    "title": title,
                    "tags": tags,
                    "related": related,
                    "sources": sources,
                    "created": str(meta.get("created") or today()),
                    "updated": today(),
                }
            )
            payload = front + "\n" + normalize_body(_strip_empty_frontmatter(body))
            workspace.write_text(relative, payload)
            written.append(relative)
            if relative == summary_expected:
                has_summary = True

        if not has_summary:
            fallback = self._ensure_summary(workspace, source_name)
            if fallback:
                written.append(fallback)
        return written

    def _ensure_summary(self, workspace: WikiWorkspace, source_name: str) -> str:
        relative = f"wiki/sources/{safe_slug(Path(source_name).stem)}.md"
        if workspace.path(relative).is_file():
            return ""
        title = Path(source_name).stem
        body = "\n".join(
            [
                f"# {title}",
                "",
                f"> 来源：`{source_name}` · 编译于 {today()}",
                "",
                "## 摘要",
                "",
                "本节未能从模型输出中获得来源摘要，已由系统补建。建议补充资料后重新编译，或手动补全要点。",
                "",
            ]
        )
        front = build_frontmatter(
            {
                "type": "source",
                "title": title,
                "tags": [],
                "related": [],
                "sources": [source_name],
                "created": today(),
                "updated": today(),
            }
        )
        workspace.write_text(relative, front + "\n" + body)
        return relative

    def embed_page(self, workspace: WikiWorkspace, relative: str) -> None:
        """把单页写入向量索引；模型不可用时不抛错，只跳过。"""
        try:
            PageVectorIndex(workspace, self.embeddings).upsert_page(relative)
        except Exception as exc:  # noqa: BLE001
            logger.debug("embed_page skipped for %s: %s", relative, exc)


def _extract_section(raw: str, heading: str) -> str:
    pattern = re.compile(rf"##\s*{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)", re.S)
    match = pattern.search(raw or "")
    return match.group(1).strip() if match else ""


def _strip_empty_frontmatter(body: str) -> str:
    return re.sub(r"\A\s*---\s*\n\s*---\s*\n", "", body or "")


def _infer_type(relative: str) -> str:
    parts = relative.split("/")
    if len(parts) >= 2:
        mapping = {
            "entities": "entity",
            "concepts": "concept",
            "sources": "source",
            "queries": "query",
            "comparisons": "comparison",
            "synthesis": "synthesis",
            "thesis": "thesis",
            "findings": "finding",
            "methodology": "methodology",
            "decisions": "decision",
            "processes": "process",
            "metrics": "metric",
        }
        return mapping.get(parts[1], "concept")
    return "concept"


def _sanitize_wiki_path(raw: str) -> str | None:
    path = (raw or "").strip().strip("`").replace("\\", "/")
    path = re.sub(r"^\./", "", path)
    if not path.endswith(".md"):
        path += ".md"
    if not path.startswith("wiki/"):
        path = f"wiki/{path.lstrip('/')}"
    if ".." in path.split("/"):
        return None
    if any(part in {"", "."} for part in path.split("/")):
        return None
    return path
