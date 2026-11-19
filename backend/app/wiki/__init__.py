"""HyperCortex LLM Wiki engine.

三层架构（沿用 Karpathy 的 LLM Wiki pattern）：
    raw/sources  不可变原始资料
    wiki/        LLM + 规则维护的结构化知识层
    purpose.md / schema.md  意图层与规则层

核心操作：ingest（编译）、query（检索/问答）、lint（质检）。
"""

from .store import WikiWorkspace, workspace_for  # noqa: F401

__all__ = ["WikiWorkspace", "workspace_for"]
