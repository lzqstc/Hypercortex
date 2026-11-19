"""知识图谱：4 信号相关性、Louvain 社区发现、图谱洞察。

为什么不用「链接数」当唯一指标：
直接链接只说明作者写过一次引用，真正相关的两页往往共享来源、共享邻居、
或者属于互补类型（实体 ↔ 概念）。四信号加权能显著提升检索扩展与洞察质量。
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Iterable

from .store import PageRecord, WikiWorkspace, extract_links

WEIGHTS = {
    "directLink": 3.0,
    "sourceOverlap": 4.0,
    "commonNeighbor": 1.5,
    "typeAffinity": 1.0,
}

TYPE_AFFINITY: dict[str, dict[str, float]] = {
    "entity": {"concept": 1.2, "entity": 0.8, "source": 1.0, "synthesis": 1.0, "query": 0.8, "finding": 1.0},
    "concept": {"entity": 1.2, "concept": 0.8, "source": 1.0, "synthesis": 1.2, "query": 1.0, "methodology": 1.1},
    "source": {"entity": 1.0, "concept": 1.0, "source": 0.5, "query": 0.8, "synthesis": 1.0, "finding": 1.0},
    "query": {"concept": 1.0, "entity": 0.8, "synthesis": 1.0, "source": 0.8, "query": 0.5, "thesis": 1.1},
    "synthesis": {"concept": 1.2, "entity": 1.0, "source": 1.0, "query": 1.0, "synthesis": 0.8, "thesis": 1.2},
    "thesis": {"finding": 1.3, "methodology": 1.1, "synthesis": 1.2, "query": 1.0, "concept": 1.1},
    "finding": {"thesis": 1.3, "methodology": 1.2, "source": 1.0, "concept": 1.0},
    "methodology": {"finding": 1.2, "concept": 1.1, "thesis": 1.1, "source": 1.0},
    "comparison": {"entity": 1.2, "concept": 1.1, "synthesis": 1.1},
    "decision": {"process": 1.1, "metric": 1.2, "entity": 1.0, "synthesis": 1.0},
    "process": {"decision": 1.1, "entity": 1.0, "metric": 1.0},
    "metric": {"decision": 1.2, "process": 1.0, "concept": 1.0},
}

STRUCTURAL = {"index", "log", "overview"}
COMMUNITY_PALETTE = [
    "#4b4ef0", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6",
    "#14b8a6", "#f97316", "#6366f1", "#84cc16", "#e11d48", "#0891b2",
]


def _affinity(type_a: str, type_b: str) -> float:
    table = TYPE_AFFINITY.get(type_a or "", {})
    if type_b in table:
        return table[type_b]
    reverse = TYPE_AFFINITY.get(type_b or "", {})
    return reverse.get(type_a, 0.6)


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).lower()


class WikiGraph:
    """由 wiki 页面即时构建的图。规模在千页级，构建成本可以接受（<50ms）。"""

    def __init__(self, records: list[PageRecord], bodies: dict[str, str]):
        self.records = [record for record in records if record.name not in STRUCTURAL]
        self.by_id: dict[str, PageRecord] = {record.name: record for record in self.records}
        self.by_title: dict[str, PageRecord] = {}
        for record in self.records:
            self.by_title.setdefault(_norm(record.title), record)
            self.by_title.setdefault(_norm(record.name), record)
        self.bodies = bodies
        self.links: dict[str, set[str]] = {record.name: set() for record in self.records}
        self.backlinks: dict[str, set[str]] = {record.name: set() for record in self.records}
        self._build_links()
        self.communities: dict[str, int] = {}
        self.cohesion: dict[int, float] = {}
        self.weights: dict[tuple[str, str], dict[str, float]] = {}

    # ------------------------------------------------------------------
    # 建图
    # ------------------------------------------------------------------
    def _resolve(self, link: str) -> str | None:
        raw = link.strip()
        if not raw:
            return None
        candidate = raw.replace("wiki/", "").replace(".md", "").split("/")[-1]
        if candidate in self.by_id:
            return candidate
        record = self.by_title.get(_norm(raw)) or self.by_title.get(_norm(candidate))
        return record.name if record else None

    def _build_links(self) -> None:
        for record in self.records:
            body = self.bodies.get(record.path, record.body)
            for link in extract_links(body):
                target = self._resolve(link)
                if not target or target == record.name:
                    continue
                self.links[record.name].add(target)
                self.backlinks[target].add(record.name)
        # related frontmatter 也算弱链接
        for record in self.records:
            for related in record.related:
                target = self._resolve(related)
                if target and target != record.name:
                    self.links[record.name].add(target)
                    self.backlinks[target].add(record.name)

    def degree(self, node: str) -> int:
        return len(self.links.get(node, ())) + len(self.backlinks.get(node, ()))

    def _neighbors(self, node: str) -> set[str]:
        return set(self.links.get(node, ())) | set(self.backlinks.get(node, ()))

    # ------------------------------------------------------------------
    # 相关性
    # ------------------------------------------------------------------
    def relevance(self, a: str, b: str) -> dict[str, float]:
        if a == b:
            return {"total": 0.0}
        rec_a, rec_b = self.by_id.get(a), self.by_id.get(b)
        if not rec_a or not rec_b:
            return {"total": 0.0}
        direct = 1.0 if (b in self.links.get(a, ()) or a in self.links.get(b, ())) else 0.0
        src_a, src_b = {_norm(item) for item in rec_a.sources}, {_norm(item) for item in rec_b.sources}
        shared_sources = len(src_a & src_b)
        source_signal = min(1.0, shared_sources / 2) if shared_sources else 0.0
        neighbors_a, neighbors_b = self._neighbors(a), self._neighbors(b)
        common = neighbors_a & neighbors_b
        adamic = 0.0
        for node in common:
            degree = max(2, len(self._neighbors(node)))
            adamic += 1.0 / math.log(degree + 1)
        adamic = min(1.0, adamic / 2)
        affinity = _affinity(rec_a.type, rec_b.type)
        total = (
            WEIGHTS["directLink"] * direct
            + WEIGHTS["sourceOverlap"] * source_signal
            + WEIGHTS["commonNeighbor"] * adamic
            + WEIGHTS["typeAffinity"] * affinity
        )
        return {
            "total": round(total, 3),
            "directLink": direct,
            "sourceOverlap": round(source_signal, 3),
            "commonNeighbor": round(adamic, 3),
            "typeAffinity": affinity,
            "sharedSources": shared_sources,
            "commonNeighbors": len(common),
        }

    def related(self, node: str, limit: int = 8) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for other in self.by_id:
            if other == node:
                continue
            detail = self.relevance(node, other)
            if detail["total"] <= 1.0:
                continue
            record = self.by_id[other]
            scored.append(
                {
                    "id": other,
                    "title": record.title,
                    "type": record.type,
                    "path": record.path,
                    "score": detail["total"],
                    "reasons": _reason_text(detail),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------
    # Louvain 社区发现
    # ------------------------------------------------------------------
    def detect_communities(self, resolution: float = 1.0) -> dict[str, int]:
        nodes = list(self.by_id)
        adjacency: dict[str, dict[str, float]] = defaultdict(dict)
        for record in self.records:
            for target in self.links.get(record.name, ()):
                if target not in self.by_id:
                    continue
                weight = 1.0 + 0.25 * (1.0 if _affinity(record.type, self.by_id[target].type) > 1 else 0.0)
                adjacency[record.name][target] = adjacency[record.name].get(target, 0.0) + weight
                adjacency[target][record.name] = adjacency[target].get(record.name, 0.0) + weight
        # 无链接节点：按类型聚类，避免全部落进 0 号社区
        isolated_by_type: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            if not adjacency.get(node):
                isolated_by_type[self.by_id[node].type or "other"].append(node)

        community = {node: index for index, node in enumerate(nodes)}
        if len(nodes) > 1:
            self._louvain(nodes, adjacency, community, resolution)

        # 重新编号，让社区按规模排序（0 = 最大社区）
        sizes: dict[int, int] = defaultdict(int)
        for value in community.values():
            sizes[value] += 1
        remap = {old: new for new, (old, _) in enumerate(sorted(sizes.items(), key=lambda item: -item[1]))}
        for node, value in list(community.items()):
            community[node] = remap[value]

        # 孤立节点各自成社区，保证洞察里能被识别为「孤立」
        next_id = (max(community.values()) + 1) if community else 0
        for node, group in isolated_by_type.items():
            if len(group) == 1:
                community[group[0]] = next_id
                next_id += 1
            else:
                for member in group:
                    community[member] = next_id
                next_id += 1

        self.communities = community
        self.cohesion = self._cohesion(community)
        return community

    @staticmethod
    def _louvain(
        nodes: list[str],
        adjacency: dict[str, dict[str, float]],
        community: dict[str, int],
        resolution: float,
    ) -> None:
        """简化版 Louvain：单层局部移动，直到模块度不再提升。"""
        m = sum(sum(neighbors.values()) for neighbors in adjacency.values()) / 2
        if m <= 0:
            return
        degree = {node: sum(adjacency.get(node, {}).values()) for node in nodes}
        total_weight = {group: 0.0 for group in set(community.values())}
        for node in nodes:
            total_weight[community[node]] += degree[node]

        improved = True
        rounds = 0
        while improved and rounds < 20:
            improved = False
            rounds += 1
            for node in nodes:
                current = community[node]
                neighbors: dict[int, float] = defaultdict(float)
                for target, weight in adjacency.get(node, {}).items():
                    neighbors[community[target]] += weight
                if not neighbors:
                    continue
                total_weight[current] -= degree[node]
                best_group, best_gain = current, 0.0
                for group, weight in neighbors.items():
                    gain = weight - resolution * degree[node] * total_weight.get(group, 0.0) / (2 * m)
                    if gain > best_gain + 1e-9:
                        best_group, best_gain = group, gain
                community[node] = best_group
                total_weight[best_group] = total_weight.get(best_group, 0.0) + degree[node]
                if best_group != current:
                    improved = True

    def _cohesion(self, community: dict[str, int]) -> dict[int, float]:
        members: dict[int, list[str]] = defaultdict(list)
        for node, group in community.items():
            members[group].append(node)
        scores: dict[int, float] = {}
        for group, nodes in members.items():
            if len(nodes) < 2:
                scores[group] = 1.0 if len(nodes) == 1 else 0.0
                continue
            nodeset = set(nodes)
            internal = 0
            for node in nodes:
                internal += len(self._neighbors(node) & nodeset)
            internal //= 2
            possible = len(nodes) * (len(nodes) - 1) / 2
            scores[group] = round(internal / possible, 3) if possible else 0.0
        return scores

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export(self, limit: int = 400, node_type: str | None = None, query: str = "") -> dict[str, Any]:
        if not self.communities:
            self.detect_communities()
        needle = _norm(query)
        selected = [
            record
            for record in self.records
            if (not node_type or record.type == node_type)
            and (not needle or needle in _norm(record.title) or needle in _norm(record.name))
        ][:limit]
        ids = {record.name for record in selected}
        nodes = [
            {
                "id": record.name,
                "label": record.title,
                "type": record.type,
                "path": record.path,
                "community": self.communities.get(record.name, 0),
                "color": COMMUNITY_PALETTE[self.communities.get(record.name, 0) % len(COMMUNITY_PALETTE)],
                "linkCount": self.degree(record.name),
                "sources": record.sources,
                "updated": record.updated,
            }
            for record in selected
        ]
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for record in selected:
            for target in self.links.get(record.name, ()):
                if target not in ids:
                    continue
                key = tuple(sorted((record.name, target)))
                if key in seen:
                    continue
                seen.add(key)
                detail = self.relevance(record.name, target)
                edges.append(
                    {
                        "source": record.name,
                        "target": target,
                        "weight": min(1.0, detail["total"] / 12.0),
                        "score": detail["total"],
                    }
                )
        community_sizes: dict[int, int] = defaultdict(int)
        for node in nodes:
            community_sizes[node["community"]] += 1
        communities = [
            {
                "id": group,
                "size": size,
                "cohesion": self.cohesion.get(group, 0.0),
                "color": COMMUNITY_PALETTE[group % len(COMMUNITY_PALETTE)],
                "label": _community_label(self, group),
            }
            for group, size in sorted(community_sizes.items(), key=lambda item: -item[1])
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "communities": communities,
            "stats": {
                "pages": len(self.records),
                "links": sum(len(value) for value in self.links.values()),
                "density": round(
                    sum(len(value) for value in self.links.values()) / max(1, len(self.records) * (len(self.records) - 1)),
                    4,
                ),
            },
        }

    # ------------------------------------------------------------------
    # 洞察
    # ------------------------------------------------------------------
    def surprising_connections(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.communities:
            self.detect_communities()
        scored: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for record in self.records:
            for target in self.links.get(record.name, ()):
                if target not in self.by_id:
                    continue
                key = tuple(sorted((record.name, target)))
                if key in seen:
                    continue
                seen.add(key)
                reasons: list[str] = []
                score = 0.0
                if self.communities.get(record.name) != self.communities.get(target):
                    score += 3
                    reasons.append("跨社区连接")
                if record.type != self.by_id[target].type:
                    score += 2
                    reasons.append("跨类型连接")
                deg_a, deg_b = self.degree(record.name), self.degree(target)
                high, low = max(deg_a, deg_b), max(1, min(deg_a, deg_b))
                if low <= 2 and high >= 5:
                    score += 2
                    reasons.append("外围节点接入枢纽")
                shared = {_norm(item) for item in record.sources} & {_norm(item) for item in self.by_id[target].sources}
                if shared:
                    score += 1
                    reasons.append("共享来源")
                if score < 3:
                    continue
                scored.append(
                    {
                        "source": record.name,
                        "sourceTitle": record.title,
                        "target": target,
                        "targetTitle": self.by_id[target].title,
                        "score": round(score, 2),
                        "reasons": reasons,
                        "key": f"{record.name}::{target}",
                    }
                )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def knowledge_gaps(self, limit: int = 8) -> list[dict[str, Any]]:
        if not self.communities:
            self.detect_communities()
        gaps: list[dict[str, Any]] = []

        for record in self.records:
            if self.degree(record.name) <= 1:
                gaps.append(
                    {
                        "type": "isolated-node",
                        "title": f"孤立页面：{record.title}",
                        "description": "该页几乎没有任何链接，知识尚未接入网络，很可能是编译时未找到关联。",
                        "nodeIds": [record.name],
                        "suggestion": "为该页补充至少 2 条交叉引用，或研究它的上下游主题",
                        "seed": record.title,
                    }
                )

        members: dict[int, list[str]] = defaultdict(list)
        for node, group in self.communities.items():
            members[group].append(node)
        for group, nodes in members.items():
            if len(nodes) >= 3 and self.cohesion.get(group, 0.0) < 0.15:
                titles = [self.by_id[node].title for node in nodes[:4]]
                gaps.append(
                    {
                        "type": "sparse-community",
                        "title": f"松散主题簇（{len(nodes)} 页，内聚度 {self.cohesion.get(group, 0.0):.2f}）",
                        "description": "这些页面被聚在一起，但彼此链接稀疏，说明主题边界还不清晰：" + "、".join(titles),
                        "nodeIds": nodes,
                        "suggestion": "补一个综合页或对比页，把这一簇的共性说清楚",
                        "seed": titles[0] if titles else "",
                    }
                )

        for node in self.by_id:
            neighbor_groups = {self.communities.get(item, -1) for item in self._neighbors(node)}
            neighbor_groups.discard(-1)
            if len(neighbor_groups) >= 3:
                gaps.append(
                    {
                        "type": "bridge-node",
                        "title": f"桥接节点：{self.by_id[node].title}",
                        "description": f"该页同时连接 {len(neighbor_groups)} 个主题簇，是跨领域枢纽，也是最值得深挖的位置。",
                        "nodeIds": [node],
                        "suggestion": "围绕它做一次深度研究，把跨领域关联写成综合页",
                        "seed": self.by_id[node].title,
                    }
                )

        order = {"bridge-node": 0, "sparse-community": 1, "isolated-node": 2}
        gaps.sort(key=lambda item: (order.get(item["type"], 9), -len(item["nodeIds"])))
        return gaps[:limit]


def _reason_text(detail: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if detail.get("directLink"):
        reasons.append("直接链接")
    if detail.get("sharedSources"):
        reasons.append(f"共享 {detail['sharedSources']} 份来源")
    if detail.get("commonNeighbors"):
        reasons.append(f"{detail['commonNeighbors']} 个共同邻居")
    if float(detail.get("typeAffinity") or 0) >= 1.1:
        reasons.append("类型互补")
    return reasons or ["弱关联"]


def _community_label(graph: WikiGraph, group: int) -> str:
    members = [graph.by_id[node] for node, value in graph.communities.items() if value == group]
    if not members:
        return f"主题簇 {group + 1}"
    members.sort(key=lambda record: graph.degree(record.name), reverse=True)
    head = members[0].title
    return head if len(members) == 1 else f"{head} 等 {len(members)} 页"


def build_graph(workspace: WikiWorkspace, records: list[PageRecord] | None = None) -> WikiGraph:
    records = records if records is not None else workspace.page_records()
    bodies = {record.path: record.body for record in records}
    return WikiGraph(records, bodies)
