"""混合检索：分词命中 + 图扩展 + 上下文预算装配。

与「把整库塞进提示词」相比，这条流水线保证：
1. 有明确命中（可解释），不是黑盒相似度；
2. 通过图谱把「没命中但强相关」的页面带进来；
3. 严格按预算装配，页面内容是完整正文而非摘要，便于模型引用。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .graph import WikiGraph
from .store import PageRecord, WikiWorkspace

STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "与", "及", "对", "为", "从", "到", "把", "被",
    "什么", "如何", "怎么", "哪些", "为什么", "是否", "可以", "需要", "这个", "那个",
    "the", "a", "an", "of", "to", "in", "is", "are", "and", "or", "for", "on", "with",
    "what", "how", "why", "which", "does", "do",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-\.\+]*|\d+(?:\.\d+)?")
_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")

try:  # pragma: no cover - 可选依赖
    import jieba  # type: ignore

    jieba.setLogLevel(60)
    _HAS_JIEBA = True
except Exception:  # noqa: BLE001
    _HAS_JIEBA = False


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    for word in _WORD_RE.findall(text):
        lowered = word.lower()
        if lowered not in STOPWORDS and len(lowered) > 1:
            tokens.append(lowered)
    for run in _CJK_RUN_RE.findall(text):
        if _HAS_JIEBA:
            pieces = [piece.strip() for piece in jieba.lcut(run) if piece.strip()]
            tokens.extend(piece for piece in pieces if piece not in STOPWORDS and len(piece) > 1)
        else:
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        # 中文名实体常被切碎，额外补 3-gram 提升召回
        if len(run) >= 3:
            tokens.extend(run[index : index + 3] for index in range(len(run) - 2))
    return [token for token in tokens if token.strip()]


@dataclass
class SearchHit:
    kind: str  # page | source | related
    id: str
    title: str
    path: str
    type: str
    score: float
    snippet: str
    content: str = ""
    reasons: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "type": self.type,
            "score": round(self.score, 3),
            "snippet": self.snippet,
            "reasons": self.reasons,
            "sources": self.sources,
        }


def _highlight(query: str, tokens: list[str], limit: int = 4) -> list[str]:
    """把命中的分词片段还原成查询里的连续短语。

    中文按 2/3-gram 切分后，「政策补贴」会同时命中「政策」「政策补」「策补贴」
    「补贴」，直接展示会变成一串碎片。这里按命中位置合并区间，只暴露用户能读懂的
    连续短语。
    """
    spans: list[list[int]] = []
    for token in set(tokens):
        if not token:
            continue
        start = query.find(token)
        while start >= 0:
            spans.append([start, start + len(token)])
            start = query.find(token, start + 1)
    if not spans:
        return []
    spans.sort()
    merged: list[list[int]] = [spans[0]]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    phrases = [query[start:end].strip() for start, end in merged]
    return [phrase for phrase in phrases if phrase][:limit]


def _prose(text: str) -> str:
    """把 markdown 页面压成纯正文：去掉 frontmatter、标题行、表格与列表符号。

    检索摘要与抽取式回答都直接展示这段文字，若保留 `## 关联`、`> 来源：` 这类
    骨架，用户看到的会是一堆排版噪声而不是知识内容。
    """
    body = re.sub(r"^---.*?---", "", text, flags=re.S)
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "|", "<!--", "```", "---")):
            continue
        line = re.sub(r"^[>\-\*\+]\s*", "", line)
        line = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", line)
        line = re.sub(r"\s*（\s*(?:wiki|raw)/[^）]*）", "", line)
        line = re.sub(r"[*_`]", "", line)
        if len(line) < 4:
            continue
        # 索引式短行（章节名、概念清单）既不是句子也不含信息，去掉避免摘要被污染
        if len(line) < 16 and "。" not in line:
            continue
        # 元信息行（来源/编译时间）与引用清单对读者没有信息量
        if line.startswith("来源：") and "编译于" in line:
            continue
        if line.count("（") >= 2 and "wiki/" in line:
            continue
        if re.match(r"^(\[\d+\]\s*)+\S", line):
            continue
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _snippet(text: str, tokens: list[str], width: int = 220) -> str:
    clean = _prose(text)
    if not clean:
        return ""
    lowered = clean.lower()
    position = -1
    best_score = -1.0
    for token in set(tokens):
        if not token:
            continue
        found = lowered.find(token)
        if found < 0:
            continue
        # 用「长度 ÷ 出现次数」挑锚点：既偏好具体的长词，又避免选到
        # 满篇都是的高频词（如「低空」），否则摘要会停在无关的第一句话上。
        score = len(token) / (1 + lowered.count(token))
        if score > best_score or (score == best_score and (position < 0 or found < position)):
            position, best_score = found, score
    if position < 0:
        return clean[:width] + ("…" if len(clean) > width else "")
    # 优先返回包含命中的完整句子，读起来比截断的字符窗口自然
    start = clean.rfind("。", 0, position + 1)
    start = 0 if start < 0 else start + 1
    end = clean.find("。", position)
    end = len(clean) if end < 0 else end + 1
    sentence = clean[start:end].strip()
    if len(sentence) <= width * 1.2 and len(sentence) >= 12:
        return sentence
    window = clean[max(0, position - width // 3) :][:width]
    return window + ("…" if len(window) >= width else "")


class WikiSearcher:
    def __init__(self, workspace: WikiWorkspace):
        self.workspace = workspace

    def _page_index(self, records: list[PageRecord]) -> tuple[dict[str, Counter], dict[str, float]]:
        df: Counter = Counter()
        bags: dict[str, Counter] = {}
        for record in records:
            body = record.body or self.workspace.read_text(record.path)
            bag = Counter(tokenize(f"{record.title} {record.title} {' '.join(record.tags)} {body}"))
            bags[record.path] = bag
            df.update(set(bag))
        total = max(1, len(records))
        idf = {token: math.log(1 + total / (1 + count)) for token, count in df.items()}
        return bags, idf

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        graph: WikiGraph | None = None,
        include_sources: bool = True,
        expand: bool = True,
    ) -> list[SearchHit]:
        tokens = tokenize(query)
        if not tokens:
            return []
        records = [record for record in self.workspace.page_records() if record.name not in {"index", "log", "overview"}]
        bags, idf = self._page_index(records)
        max_score = 0.0
        hits: dict[str, SearchHit] = {}
        for record in records:
            bag = bags.get(record.path, Counter())
            if not bag:
                continue
            score = 0.0
            matched: list[str] = []
            for token in set(tokens):
                count = bag.get(token, 0)
                if not count:
                    continue
                weight = idf.get(token, 1.0) * (1 + math.log(count))
                score += weight
                matched.append(token)
            if score <= 0:
                continue
            title_lower = record.title.lower()
            for token in set(tokens):
                if token and token in title_lower:
                    score += 10.0
            if record.name.lower() in query.lower():
                score += 8.0
            max_score = max(max_score, score)
            hits[record.path] = SearchHit(
                kind="page",
                id=record.name,
                title=record.title,
                path=record.path,
                type=record.type,
                score=score,
                snippet=_snippet(record.body or self.workspace.read_text(record.path), tokens),
                content=record.body,
                reasons=[f"命中：{'、'.join(_highlight(query, matched))}"],
                sources=record.sources,
            )

        if include_sources:
            for path in self.workspace.source_files():
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if path.suffix.lower() not in {".md", ".txt", ".markdown", ".csv", ".json"}:
                    continue
                bag = Counter(tokenize(text[:200000]))
                score = 0.0
                for token in set(tokens):
                    count = bag.get(token, 0)
                    if count:
                        score += idf.get(token, 1.0) * (1 + math.log(count)) * 0.6
                if score <= 0:
                    continue
                relative = path.relative_to(self.workspace.root).as_posix()
                hits[relative] = SearchHit(
                    kind="source",
                    id=path.stem,
                    title=path.name,
                    path=relative,
                    type="source-file",
                    score=score,
                    snippet=_snippet(text, tokens),
                    content="",
                    reasons=["原始资料命中"],
                )

        ranked = sorted(hits.values(), key=lambda item: item.score, reverse=True)[:limit]

        if expand and graph is not None and ranked:
            existing = {hit.id for hit in ranked}
            extra: list[SearchHit] = []
            for hit in ranked[:3]:
                for related in graph.related(hit.id, limit=3):
                    if related["id"] in existing:
                        continue
                    record = graph.by_id.get(related["id"])
                    if not record:
                        continue
                    existing.add(related["id"])
                    extra.append(
                        SearchHit(
                            kind="related",
                            id=record.name,
                            title=record.title,
                            path=record.path,
                            type=record.type,
                            score=related["score"] * 0.5,
                            snippet=_snippet(record.body, tokens),
                            content=record.body,
                            reasons=[f"图谱扩展：{'、'.join(related['reasons'])}"],
                            sources=record.sources,
                        )
                    )
            ranked = sorted(ranked + extra, key=lambda item: item.score, reverse=True)

        if max_score > 0:
            for hit in ranked:
                hit.score = round(hit.score / max_score, 3)
        return ranked

    # ------------------------------------------------------------------
    # 上下文装配
    # ------------------------------------------------------------------
    def build_context(
        self,
        hits: list[SearchHit],
        *,
        max_chars: int = 24000,
    ) -> tuple[str, list[dict[str, object]]]:
        blocks: list[str] = []
        used: list[dict[str, object]] = []
        remaining = max_chars
        for index, hit in enumerate(hits, start=1):
            body = hit.content
            if not body and hit.kind == "source":
                body = self.workspace.read_text(hit.path)[:8000]
            if not body:
                continue
            allowance = min(len(body), max(600, remaining - 400))
            if allowance <= 0:
                break
            snippet = body[:allowance]
            header = f"[{index}] {hit.title}（{hit.type or hit.kind}）路径：{hit.path}"
            block = f"{header}\n{snippet}"
            blocks.append(block)
            used.append(
                {
                    "index": index,
                    "id": hit.id,
                    "title": hit.title,
                    "path": hit.path,
                    "type": hit.type or hit.kind,
                    "sources": hit.sources,
                    "score": hit.score,
                    "reason": hit.reasons,
                }
            )
            remaining -= len(block) + 2
            if remaining <= 600:
                break
        return "\n\n".join(blocks), used

    # ------------------------------------------------------------------
    # 来源（raw）全文
    # ------------------------------------------------------------------
    def source_text(self, relative: str, limit: int = 60000) -> str:
        path = self.workspace.path(relative)
        if not path.is_file():
            return ""
        if path.suffix.lower() in {".md", ".txt", ".markdown", ".csv", ".json"}:
            return path.read_text(encoding="utf-8", errors="ignore")[:limit]
        return ""


def context_budget(tokens: int) -> dict[str, int]:
    """60% 页面 / 20% 对话历史 / 5% 索引 / 15% 系统提示。"""
    tokens = max(4000, min(1_000_000, int(tokens or 32000)))
    chars = int(tokens * 1.7)
    return {
        "tokens": tokens,
        "chars": chars,
        "pages": int(chars * 0.60),
        "history": int(chars * 0.20),
        "index": int(chars * 0.05),
        "system": int(chars * 0.15),
    }


def guess_reading_order(workspace: WikiWorkspace, record: PageRecord) -> dict[str, object]:
    path = Path(record.path)
    return {"dir": path.parent.name, "file": path.name}
