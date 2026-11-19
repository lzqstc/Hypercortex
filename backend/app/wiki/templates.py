"""项目模板：purpose.md（意图层）与 schema.md（规则层）。

purpose.md 说明「为什么存在、要回答什么」，schema.md 说明「页面怎么组织」。
LLM 在每次 ingest / query 时都会读取这两份文件作为上下文，
因此它们是决定编译质量的关键资产，而不是装饰性文档。
"""

from __future__ import annotations

from dataclasses import dataclass, field

BASE_TYPES = """| type | 目录 | 用途 |
| --- | --- | --- |
| entity | wiki/entities/ | 具名事物：人物、组织、产品、系统、数据集 |
| concept | wiki/concepts/ | 概念、方法、技术、框架、现象 |
| source | wiki/sources/ | 单份原始资料的摘要页（每个来源必须有且仅有一个） |
| query | wiki/queries/ | 正在追踪的开放问题、研究任务与结论 |
| comparison | wiki/comparisons/ | 两个及以上对象的并列对比 |
| synthesis | wiki/synthesis/ | 跨来源的综合分析、判断与结论 |
| overview | wiki/ | 全库总览（系统自动维护，勿手写） |"""

BASE_NAMING = """- 拉丁文文件名用 `kebab-case.md`，中文/日文/韩文标题保留原文字符，不转拼音、不译成英文
- 实体优先使用官方名称：`openai.md`、`gpt-5.md`、`sap-s4hana.md`
- 概念使用描述性名词短语：`chain-of-thought.md`、`需求价格弹性.md`
- 来源摘要：`作者-年份-短标题.md`，无作者时用 `年份-短标题.md`
- 问题：把问题写成 slug：`规模是否提升推理能力.md`
- 专有名词、模型名、数据集名、库名、代码标识符保留原始写法"""

BASE_FRONTMATTER = """所有页面必须带 YAML frontmatter（解析器严格，首行必须是 `---`）：

```yaml
---
type: entity
title: 人类可读标题
tags: [标签1, 标签2]
related: [slug-a, slug-b]
sources: ["原始文件名.pdf"]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

字段规则：
- `type` 必须与所在目录对应；`related` 只写裸 slug，不写 `wiki/`、`.md`、`[[...]]`
- `sources` 记录该页结论的原始依据，便于溯源与级联清理
- wikilink 只写在正文：`[[页面标题]]`"""

BASE_INDEX = """`wiki/index.md` 按类型分组列出全部页面，每条一行：

```
- [[page-slug]] — 一句话说明
```"""

BASE_LOG = """`wiki/log.md` 以时间倒序记录操作，可被程序解析：

```
## 2025-01-01

- ingest | 资料名 | 新建 3 页 · 更新 1 页
```"""

BASE_CROSSREF = """- 正文用 `[[页面标题]]` 建立交叉引用，链接到尚不存在的页面是允许的（会成为待建页线索）
- 每个实体页与概念页都应被 `index.md` 收录
- 问题页链接它依赖的来源与概念；综合页在 `related` 中列出全部贡献来源
- 出现矛盾时：在相关页注明冲突 → 建/更新问题页追踪 → 证据充分后在综合页给出判断"""

BASE_CONTRADICTION = """## 矛盾处理

1. 在相关实体/概念页明确标注「来源 A 与来源 B 在此点上不一致」，各自给出处
2. 建立或更新问题页追踪该分歧，把双方来源都链上
3. 证据足够后，在综合页给出判断并说明置信度
4. 不得为了「看起来一致」而删除其中一方"""


@dataclass(frozen=True)
class WikiTemplate:
    id: str
    name: str
    description: str
    icon: str
    purpose: str
    schema: str
    extra_dirs: tuple[str, ...] = field(default_factory=tuple)


def _schema(title: str, types_extra: str = "", naming_extra: str = "", extra_sections: str = "") -> str:
    parts = [
        f"# Wiki Schema — {title}",
        "",
        "## 页面类型与路由",
        "",
        BASE_TYPES + (("\n" + types_extra) if types_extra else ""),
        "",
        "> Wiki 只收「知识」，不收操作日志、草稿、待办清单。原始资料保持不可变，所有加工都在 wiki/ 内完成。",
        "",
        "## 命名规范",
        "",
        BASE_NAMING + (("\n" + naming_extra) if naming_extra else ""),
        "",
        "## Frontmatter",
        "",
        BASE_FRONTMATTER,
        "",
        "## 索引格式",
        "",
        BASE_INDEX,
        "",
        "## 日志格式",
        "",
        BASE_LOG,
        "",
        "## 交叉引用规则",
        "",
        BASE_CROSSREF,
        "",
        BASE_CONTRADICTION,
    ]
    if extra_sections:
        parts.extend(["", extra_sections])
    return "\n".join(parts) + "\n"


RESEARCH_PURPOSE = """# 研究意图

## 这个知识库为什么存在

把分散的论文、报告、访谈与网页资料，编译成一个**可推理、可溯源、会自我修正**的研究底座，
让每一次提问都能落在证据上，而不是落在模型的记忆里。

## 要回答的核心问题

1. 这批材料共同支持了什么结论？证据强度如何？
2. 哪些结论之间存在冲突？冲突来自数据、口径，还是方法？
3. 还有哪些关键问题没有材料支撑（知识缺口）？
4. 如果要把结论用于决策，最薄弱的一环在哪里？

## 范围

- 收录：与研究主题直接相关的原始资料、可复用的方法与测量口径
- 排除：纯宣传材料、无法溯源的数据、与主题无关的行业新闻
- 语言：正文简体中文；专有名词、模型名、指标名保留原文

## 演进中的论点

随材料增加持续更新。论点页放在 `wiki/thesis/`，状态用 `speculative / supported / refuted / settled` 标注，
被推翻的论点保留在库中并注明反证，这是研究过程的一部分。

## 质量底线

- 任何结论必须能在 `sources` 找到出处
- 不确定就写不确定，禁止用流畅的措辞掩盖证据缺口
- 数字、口径、时间范围必须与原文一致，不得四舍五入后当作原文数据
"""

RESEARCH_SCHEMA = _schema(
    "研究型知识库",
    types_extra=(
        "| thesis | wiki/thesis/ | 工作中的假设及其演变（frontmatter 加 `confidence`、`status`） |\n"
        "| methodology | wiki/methodology/ | 研究方法、协议、实验设计、测量口径 |\n"
        "| finding | wiki/findings/ | 单条实证结果或观察（frontmatter 加 `source`、`replicated`） |"
    ),
    naming_extra=(
        "- 论点：假设即 slug，如 `规模提升推理能力.md`\n"
        "- 方法：方法名，如 `系统综述.md`、`消融实验.md`\n"
        "- 发现：描述性 slug，如 `大模型少样本表现更好.md`"
    ),
    extra_sections="""## 研究型知识库的额外要求

- 论点页必须写明：主张、支持证据、反证、当前状态、下一步验证动作
- 发现页必须写明：样本/数据范围、测量方式、效应方向与量级、可否复现
- 方法页必须写明：适用条件与失效边界，避免方法被无条件套用
""",
)

READING_PURPOSE = """# 阅读意图

## 这个知识库为什么存在

把读过的书、文章、长视频，压缩成可以反复调用的结构化理解，而不是一堆读完就忘的摘录。

## 要回答的核心问题

1. 这本书/这篇文章到底主张什么？论证链条是什么？
2. 哪些观点与我已有的理解冲突或互补？
3. 有哪些可以直接拿来用的模型、清单、方法？
4. 哪些地方我其实没读懂？

## 范围

- 收录：书籍、长文、课程、访谈
- 排除：碎片化信息流、无来源的二手转述
- 语言：正文简体中文，原名与术语保留原文

## 质量底线

- 区分「作者说的」与「我理解的」，后者必须标注
- 引用原句时保留页码/章节位置
"""

READING_SCHEMA = _schema(
    "阅读型知识库",
    types_extra="| author | wiki/entities/ | 作者、译者、受访者 |",
    naming_extra="- 书籍摘要：`作者-年份-书名.md`",
    extra_sections="""## 阅读型知识库的额外要求

- 摘要页必须包含：核心主张、论证结构、关键概念、可操作结论、保留意见
- 摘录必须可定位（页码/章节），否则视为无效摘录
""",
)

BUSINESS_PURPOSE = """# 业务知识库意图

## 这个知识库为什么存在

把产品、客户、流程、竞品与决策记录沉淀为统一口径的组织记忆，
让新人一周内能查到「我们为什么这么做」，让决策有据可查。

## 要回答的核心问题

1. 这个功能/流程的设计动机与约束是什么？
2. 客户反复提出的问题集中在哪？哪些已被解决？
3. 竞品在关键维度上的差异是什么？我们的取舍是什么？
4. 哪些决策已经过期，需要重新评估？

## 范围

- 收录：产品文档、需求与评审记录、客户反馈、竞品资料、运营数据说明
- 排除：个人情绪化评价、未经确认的口头结论
- 语言：正文简体中文，产品名与指标名保留原文

## 质量底线

- 决策类页面必须写明决策日期、决策人、约束条件与替代方案
- 数据类结论必须标注口径与时间范围
"""

BUSINESS_SCHEMA = _schema(
    "业务型知识库",
    types_extra=(
        "| decision | wiki/decisions/ | 决策记录：背景、选项、取舍、结论、复盘 |\n"
        "| process | wiki/processes/ | 流程、规范、SOP |\n"
        "| metric | wiki/metrics/ | 指标定义、口径、计算方式 |"
    ),
    naming_extra=(
        "- 决策：`决策-主题.md`，如 `决策-定价分层引入用量阶梯.md`\n"
        "- 流程：流程名，如 `需求评审流程.md`"
    ),
    extra_sections="""## 业务型知识库的额外要求

- 决策页 frontmatter 增加 `status: proposed | adopted | superseded`、`owner`
- 指标页 frontmatter 增加 `formula`、`owner`，口径变更必须写变更记录
""",
)

GENERAL_PURPOSE = """# 知识库意图

## 这个知识库为什么存在

把长期积累的资料整理成可检索、可追溯、可复用的个人知识底座。

## 要回答的核心问题

1. 我在这批材料里反复关注的主题是什么？
2. 哪些结论有明确出处，哪些只是印象？
3. 还有哪些内容只是收藏、从未真正消化？

## 质量底线

- 结论必须有出处
- 不确定就标注不确定
"""

GENERAL_SCHEMA = _schema("通用知识库")


TEMPLATES: dict[str, WikiTemplate] = {
    "research": WikiTemplate(
        id="research",
        name="研究型",
        description="深度研究：假设追踪、方法记录、实证发现",
        icon="🔬",
        purpose=RESEARCH_PURPOSE,
        schema=RESEARCH_SCHEMA,
        extra_dirs=("wiki/thesis", "wiki/findings", "wiki/methodology"),
    ),
    "reading": WikiTemplate(
        id="reading",
        name="阅读型",
        description="书籍与长文的结构化理解与可复用结论",
        icon="📖",
        purpose=READING_PURPOSE,
        schema=READING_SCHEMA,
        extra_dirs=("wiki/authors",),
    ),
    "business": WikiTemplate(
        id="business",
        name="业务型",
        description="产品、流程、决策与指标的组织记忆",
        icon="🏢",
        purpose=BUSINESS_PURPOSE,
        schema=BUSINESS_SCHEMA,
        extra_dirs=("wiki/decisions", "wiki/processes", "wiki/metrics"),
    ),
    "general": WikiTemplate(
        id="general",
        name="通用型",
        description="通用个人知识底座",
        icon="🧠",
        purpose=GENERAL_PURPOSE,
        schema=GENERAL_SCHEMA,
        extra_dirs=(),
    ),
}

DEFAULT_TEMPLATE = "research"


def resolve_template(name: str | None) -> WikiTemplate:
    """把用户填写的模板名（可能是中文旧名）映射到内置模板。"""
    raw = (name or "").strip().lower()
    aliases = {
        "研究": "research",
        "研究型": "research",
        "research": "research",
        "阅读": "reading",
        "阅读型": "reading",
        "reading": "reading",
        "业务": "business",
        "业务型": "business",
        "企业知识库": "business",
        "产品知识库": "business",
        "business": "business",
        "通用": "general",
        "通用型": "general",
        "general": "general",
    }
    return TEMPLATES.get(aliases.get(raw, ""), TEMPLATES[DEFAULT_TEMPLATE])


def template_list() -> list[dict[str, str]]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "icon": item.icon,
        }
        for item in TEMPLATES.values()
    ]
