"""深度研究（Deep Research）：主题优化 → 多路检索 → 正文抽取 → 综合成页 → 自动归档。

与普通问答的差别：
- 提问会被改写成多条「可检索」的检索式，而不是直接丢给搜索引擎
- 抓取的是网页正文（不截断摘要），因此结论可核验
- 产出物是一个带引用的 wiki 页面，并可选把网页原件存入 raw/sources 后自动编译
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..services.parsers import ParserError, _validate_public_url
from .llm import LLMBridge
from .store import WikiWorkspace, build_frontmatter, normalize_body, safe_slug, today, utcnow

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; HyperCortexResearch/1.0; +https://hypercortex.local)"
MAX_QUERIES = 5
MAX_PAGES = 8
MAX_PAGE_CHARS = 20000

_STEP_KEYS = ["plan", "search", "extract", "synthesize", "ingest"]
_STEP_LABELS = {
    "plan": "拆解主题并生成检索式",
    "search": "多路网络检索",
    "extract": "抽取网页正文",
    "synthesize": "综合并写出研究页",
    "ingest": "归档原始网页并编译",
}


def _steps(current: str, done: bool = True, next_key: str | None = None) -> list[dict[str, str]]:
    """把「当前推进到哪一步」翻译成前端可直接渲染的步骤状态。"""
    current_index = _STEP_KEYS.index(current) if current in _STEP_KEYS else 0
    result: list[dict[str, str]] = []
    for index, key in enumerate(_STEP_KEYS):
        if index < current_index:
            status = "done"
        elif index == current_index:
            status = "done" if done else "running"
        elif key == next_key:
            status = "running"
        else:
            status = "pending"
        result.append({"key": key, "label": _STEP_LABELS[key], "status": status})
    return result


def _fail_steps(steps: list[dict[str, str]]) -> list[dict[str, str]]:
    """失败时把「正在跑」的那一步标成 error，其余未开始的保持 pending。"""
    result: list[dict[str, str]] = []
    marked = False
    for step in steps:
        if step.get("status") == "running":
            result.append({**step, "status": "pending" if marked else "error"})
            marked = True
        else:
            result.append(step)
    return result


class SearchError(RuntimeError):
    pass


class DeepResearchService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = LLMBridge(settings)
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def list_tasks(self, workspace: WikiWorkspace) -> list[dict[str, Any]]:
        data = workspace.read_json(".llm-wiki/research.json", [])
        items = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return sorted(items, key=lambda item: str(item.get("createdAt") or ""), reverse=True)

    def get_task(self, workspace: WikiWorkspace, task_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_tasks(workspace) if item.get("id") == task_id), None)

    def _save(self, workspace: WikiWorkspace, task: dict[str, Any]) -> None:
        items = self.list_tasks(workspace)
        replaced = False
        for index, item in enumerate(items):
            if item.get("id") == task.get("id"):
                items[index] = task
                replaced = True
                break
        if not replaced:
            items.insert(0, task)
        workspace.write_json(".llm-wiki/research.json", items[:60])

    def _patch(self, workspace: WikiWorkspace, task_id: str, **fields: Any) -> dict[str, Any]:
        task = self.get_task(workspace, task_id) or {"id": task_id}
        task.update(fields)
        task["updatedAt"] = utcnow()
        self._save(workspace, task)
        return task

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------
    async def start(
        self,
        workspace: WikiWorkspace,
        topic: str,
        *,
        seed_pages: list[str] | None = None,
        auto_ingest: bool = True,
    ) -> dict[str, Any]:
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("研究主题不能为空")
        task = {
            "id": f"res_{uuid.uuid4().hex[:10]}",
            "projectId": workspace.project_id,
            "topic": topic,
            "status": "running",
            "stage": "理解主题",
            "progress": 5,
            "steps": [
                {"key": "plan", "label": "拆解主题并生成检索式", "status": "running"},
                {"key": "search", "label": "多路网络检索", "status": "pending"},
                {"key": "extract", "label": "抽取网页正文", "status": "pending"},
                {"key": "synthesize", "label": "综合并写出研究页", "status": "pending"},
                {"key": "ingest", "label": "归档原始网页并编译", "status": "pending"},
            ],
            "queries": [],
            "sources": [],
            "pagePath": "",
            "content": "",
            "gaps": [],
            "autoIngest": auto_ingest,
            "seedPages": seed_pages or [],
            "createdAt": utcnow(),
            "updatedAt": utcnow(),
        }
        self._save(workspace, task)
        runner = asyncio.create_task(self._run(workspace, task["id"]))
        self._tasks[task["id"]] = runner
        runner.add_done_callback(lambda _: self._tasks.pop(task["id"], None))
        return task

    async def _run(self, workspace: WikiWorkspace, task_id: str) -> None:
        try:
            await asyncio.to_thread(self._execute, workspace, task_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Deep research failed: %s", task_id)
            task = self.get_task(workspace, task_id) or {}
            self._patch(
                workspace,
                task_id,
                status="error",
                stage="失败",
                error=str(exc)[:400],
                progress=100,
                steps=_fail_steps(task.get("steps") or []),
            )

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def _execute(self, workspace: WikiWorkspace, task_id: str) -> None:
        task = self.get_task(workspace, task_id)
        if not task:
            return
        topic = str(task["topic"])
        workspace.ensure()

        queries = self._plan_queries(workspace, topic, task.get("seedPages") or [])
        self._patch(
            workspace,
            task_id,
            queries=queries,
            stage="多路网络检索",
            progress=20,
            steps=_steps("plan", done=True, next_key="search"),
        )

        results: list[dict[str, Any]] = []
        errors: list[str] = []
        for query in queries:
            try:
                results.extend(self._search(query))
            except SearchError as exc:
                errors.append(f"{query}：{exc}")
            if len(results) >= MAX_PAGES * 2:
                break
        if not results:
            raise SearchError(
                "网络检索不可用。请配置 SEARCH_PROVIDER（tavily / serpapi / searxng / duckduckgo）后重试；"
                "当前也可先用知识库内检索完成研究。"
                + (f"（{errors[0]}）" if errors else "")
            )

        self._patch(
            workspace,
            task_id,
            stage="抽取网页正文",
            progress=45,
            steps=_steps("search", done=True, next_key="extract"),
        )

        documents: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for item in results:
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            content = item.get("content") or ""
            if len(content) < 400:
                try:
                    content = self._fetch_text(url)
                except Exception:  # noqa: BLE001
                    content = content or ""
            if len(content) < 300:
                continue
            documents.append(
                {
                    "url": url,
                    "title": item.get("title") or url,
                    "content": content[:MAX_PAGE_CHARS],
                    "published": item.get("published") or "",
                }
            )
            if len(documents) >= MAX_PAGES:
                break

        if not documents:
            raise SearchError("检索到的页面正文不足，无法形成可靠结论，请更换主题措辞或配置更强的检索源")

        self._patch(
            workspace,
            task_id,
            stage="综合结论",
            progress=65,
            sources=[
                {"index": index, "title": doc["title"], "url": doc["url"]}
                for index, doc in enumerate(documents, start=1)
            ],
            steps=_steps("extract", done=True, next_key="synthesize"),
        )

        internal = self._internal_context(workspace, topic)
        content, gaps = self._synthesize(workspace, topic, documents, internal)
        page_path = self._write_page(workspace, topic, content, documents)

        self._patch(
            workspace,
            task_id,
            stage="归档原始网页",
            progress=85,
            content=content,
            pagePath=page_path,
            gaps=gaps,
            steps=_steps("synthesize", done=True, next_key="ingest"),
        )

        archived: list[str] = []
        if task.get("autoIngest", True):
            archived = self._archive_sources(workspace, topic, documents)

        workspace.rebuild_index()
        workspace.rebuild_overview()
        workspace.append_log("research", topic[:60], f"检索 {len(queries)} 路 · 采用 {len(documents)} 篇 · 归档 {len(archived)} 份")
        self._patch(
            workspace,
            task_id,
            status="completed",
            stage="已完成",
            progress=100,
            archivedSources=archived,
            steps=_steps("ingest", done=True),
        )

    # ------------------------------------------------------------------
    # 规划
    # ------------------------------------------------------------------
    def _plan_queries(self, workspace: WikiWorkspace, topic: str, seeds: list[str]) -> list[str]:
        queries: list[str] = []
        if self.llm.available():
            prompt = "\n".join(
                [
                    "把下面的研究主题拆成 3-5 条适合搜索引擎的检索式。",
                    "要求：每条 6-18 个词；覆盖不同侧面（现状 / 证据 / 方法 / 反例 / 数据）；",
                    "不要写问句，不要写论文标题，不要包含「综述」「研究」这类无信息量的词堆。",
                    f"研究主题：{topic}",
                    f"知识库已有相关页面：{'、'.join(seeds[:5]) or '无'}",
                    "",
                    '只输出 JSON：{"queries": ["...", "..."]}',
                ]
            )
            try:
                data = self.llm.json_object(prompt, max_tokens=600)
                raw = data.get("queries") or data.get("items") or []
                if isinstance(raw, list):
                    queries = [str(item).strip() for item in raw if str(item).strip()]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Query planning failed: %s", exc)
        if not queries:
            base = re.sub(r"[？?！!。]+$", "", topic.strip())
            queries = [
                base,
                f"{base} 最新进展 数据",
                f"{base} 方法 局限 争议",
                f"{base} 案例 实践",
            ]
        deduped: list[str] = []
        for query in queries:
            if query not in deduped:
                deduped.append(query)
        return deduped[:MAX_QUERIES]

    def _internal_context(self, workspace: WikiWorkspace, topic: str) -> str:
        from .search import WikiSearcher

        try:
            hits = WikiSearcher(workspace).search(topic, limit=4, expand=False)
        except Exception:  # noqa: BLE001
            return ""
        if not hits:
            return ""
        blocks = [f"- {hit.title}（{hit.path}）：{hit.snippet[:200]}" for hit in hits]
        return "知识库已有相关内容：\n" + "\n".join(blocks)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def _search(self, query: str) -> list[dict[str, Any]]:
        provider = (self.settings.search_provider or "none").lower()
        if provider == "tavily" and self.settings.tavily_api_key:
            return self._search_tavily(query)
        if provider == "serpapi" and self.settings.serpapi_api_key:
            return self._search_serpapi(query)
        if provider == "searxng" and self.settings.searxng_url:
            return self._search_searxng(query)
        if provider in {"duckduckgo", "ddg", "auto", "none"}:
            try:
                return self._search_duckduckgo(query)
            except Exception as exc:  # noqa: BLE001
                raise SearchError(f"DuckDuckGo 检索失败：{exc}") from exc
        raise SearchError(f"检索服务未配置（当前 SEARCH_PROVIDER={provider}）")

    def _search_tavily(self, query: str) -> list[dict[str, Any]]:
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5,
            "include_raw_content": True,
        }
        with httpx.Client(timeout=45) as client:
            response = client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()
        return [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("raw_content") or item.get("content") or "",
                "published": item.get("published_date") or "",
            }
            for item in data.get("results", [])
        ]

    def _search_serpapi(self, query: str) -> list[dict[str, Any]]:
        params = {"q": query, "engine": "google", "api_key": self.settings.serpapi_api_key, "num": 8}
        with httpx.Client(timeout=45) as client:
            response = client.get("https://serpapi.com/search.json", params=params)
            response.raise_for_status()
            data = response.json()
        return [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "content": item.get("snippet") or "",
                "published": item.get("date") or "",
            }
            for item in data.get("organic_results", [])
        ]

    def _search_searxng(self, query: str) -> list[dict[str, Any]]:
        url = self.settings.searxng_url.rstrip("/") + "/search"
        with httpx.Client(timeout=45) as client:
            response = client.get(url, params={"q": query, "format": "json"})
            response.raise_for_status()
            data = response.json()
        return [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content") or "",
                "published": item.get("publishedDate") or "",
            }
            for item in data.get("results", [])
        ]

    def _search_duckduckgo(self, query: str) -> list[dict[str, Any]]:
        from bs4 import BeautifulSoup

        with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            response = client.post("https://html.duckduckgo.com/html/", data={"q": query})
            response.raise_for_status()
            html = response.text
        soup = BeautifulSoup(html, "lxml")
        results: list[dict[str, Any]] = []
        for node in soup.select(".result"):
            link = node.select_one(".result__a")
            snippet = node.select_one(".result__snippet")
            if not link:
                continue
            href = link.get("href") or ""
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                from urllib.parse import unquote

                href = unquote(match.group(1))
            if not href.startswith("http"):
                continue
            results.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "url": href,
                    "content": snippet.get_text(" ", strip=True) if snippet else "",
                }
            )
            if len(results) >= 6:
                break
        return results

    def _fetch_text(self, url: str) -> str:
        try:
            _validate_public_url(url, self.settings.allow_private_urls)
        except ParserError as exc:
            raise SearchError(str(exc)) from exc
        with httpx.Client(
            timeout=self.settings.url_timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
        try:
            import trafilatura

            extracted = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
        except Exception:  # noqa: BLE001
            extracted = ""
        if len(extracted) >= 300:
            return extracted
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))

    # ------------------------------------------------------------------
    # 综合
    # ------------------------------------------------------------------
    def _synthesize(
        self,
        workspace: WikiWorkspace,
        topic: str,
        documents: list[dict[str, Any]],
        internal: str,
    ) -> tuple[str, list[str]]:
        if self.llm.available():
            try:
                content = self._synthesize_with_llm(workspace, topic, documents, internal)
                if content.strip():
                    return content, []
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM synthesis failed: %s", exc)
        return self._synthesize_heuristic(topic, documents, internal)

    def _synthesize_with_llm(
        self,
        workspace: WikiWorkspace,
        topic: str,
        documents: list[dict[str, Any]],
        internal: str,
    ) -> str:
        blocks = []
        for index, doc in enumerate(documents, start=1):
            blocks.append(f"[{index}] {doc['title']}（{doc['url']}）\n{doc['content'][:6000]}")
        prompt = "\n".join(
            [
                "你在为一个研究型 wiki 撰写一份研究页。",
                "",
                "## 要求",
                "- 只使用下面给出的网页材料，不得补充外部知识；材料不足就明确写「证据不足」",
                "- 每一个关键结论后用 [编号] 标注来源，编号对应下面的材料编号",
                "- 结构：一句话结论 / 主要发现（分点）/ 证据强度与口径 / 分歧与反例 / 知识缺口 / 下一步验证动作",
                "- 使用简体中文；专有名词、机构名、模型名保留原文",
                "- 不要写「本文」「综上所述」这类空话，直接给判断",
                "",
                "## 研究主题",
                topic,
                "",
                "## 知识库内部上下文",
                internal or "（无）",
                "",
                "## 网页材料",
                "\n\n".join(blocks)[:26000],
                "",
                "只输出研究页正文（Markdown），不要 frontmatter，不要代码围栏包裹全文。",
            ]
        )
        return self.llm.chat(
            [
                {"role": "system", "content": "你是严谨的研究助理，结论必须落在证据上。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=3000,
            timeout=300,
        )

    def _synthesize_heuristic(
        self,
        topic: str,
        documents: list[dict[str, Any]],
        internal: str,
    ) -> tuple[str, list[str]]:
        from .search import tokenize

        tokens = set(tokenize(topic))

        def sentences(text: str) -> list[str]:
            parts = re.split(r"(?<=[。！？；!?;\n])", text)
            return [re.sub(r"\s+", " ", part).strip() for part in parts if 20 <= len(part.strip()) <= 300]

        findings: list[str] = []
        for index, doc in enumerate(documents, start=1):
            candidates = sentences(doc["content"])
            scored = sorted(
                candidates,
                key=lambda sentence: sum(1 for token in tokens if token in sentence.lower()),
                reverse=True,
            )
            for sentence in scored[:2]:
                findings.append(f"- {sentence} [{index}]")
            if len(findings) >= 12:
                break

        domains = sorted({urlparse(doc["url"]).netloc for doc in documents})
        lines = [
            f"# {topic}",
            "",
            f"> 由 HyperCortex 深度研究生成（{today()}）。自动抽取式综合，用于快速建立证据地图；"
            "建议配置 LLM 后重新研究以获得判断性结论。",
            "",
            "## 一句话结论",
            "",
            f"围绕「{topic}」，本次共采集 {len(documents)} 篇公开材料（{len(domains)} 个站点）。"
            "以下为按主题相关度排序的原文要点，结论需要人工复核。",
            "",
            "## 主要发现",
            "",
            *(findings or ["- 材料中未抽取到与主题直接相关的完整论断，建议更换检索式。"]),
            "",
            "## 材料来源",
            "",
        ]
        for index, doc in enumerate(documents, start=1):
            lines.append(f"{index}. [{doc['title']}]({doc['url']})")
        if internal:
            lines.extend(["", "## 与知识库的连接", "", internal])
        lines.extend(
            [
                "",
                "## 知识缺口",
                "",
                "- 缺少可量化数据支撑的结论（自动抽取无法判断证据强度）",
                "- 未覆盖反例与失败案例",
                "- 未确认各来源的口径与时间范围是否一致",
                "",
            ]
        )
        gaps = ["补充量化数据来源", "检索反例与失败案例", "核对各来源口径与时间范围"]
        return "\n".join(lines), gaps

    # ------------------------------------------------------------------
    # 落盘
    # ------------------------------------------------------------------
    def _write_page(
        self,
        workspace: WikiWorkspace,
        topic: str,
        content: str,
        documents: list[dict[str, Any]],
    ) -> str:
        title = topic if len(topic) <= 60 else topic[:58] + "…"
        slug = safe_slug(title)
        sources = [f"web:{urlparse(doc['url']).netloc}" for doc in documents]
        return workspace.write_page(
            "query",
            title,
            content,
            tags=["深度研究"],
            sources=sources,
            slug=slug,
        )

    def _archive_sources(
        self,
        workspace: WikiWorkspace,
        topic: str,
        documents: list[dict[str, Any]],
    ) -> list[str]:
        """把网页正文存成 raw/sources 下的 markdown，交给统一摄取流程编译。"""
        archived: list[str] = []
        prefix = safe_slug(topic)[:40]
        for index, doc in enumerate(documents, start=1):
            name = f"web-{prefix}-{index}.md"
            relative = f"raw/sources/{name}"
            target = workspace.path(relative)
            if target.exists():
                continue
            body = "\n".join(
                [
                    f"# {doc['title']}",
                    "",
                    f"> 来源：{doc['url']}",
                    f"> 抓取时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
                    "",
                    doc["content"],
                ]
            )
            workspace.write_text(relative, body)
            archived.append(relative)
        return archived
