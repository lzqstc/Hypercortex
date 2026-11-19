# HyperCortex

Hypercortex 是一个面向研究与企业的个人知识底座：把分散的资料编译成**可推理、可溯源、会自我维护**的结构化知识库，再用它回答问题、发现矛盾、指出知识缺口。

它由两条能力线组成：

- **RAG 知识库**：多格式解析 → 切片 → 向量 + BM25 混合检索 → 重排 → 带引用问答
- **LLM Wiki 编译层**：资料 → 两步式思维链编译 → 结构化 wiki 页面（实体/概念/来源/问题/综合）→ 图谱洞察 → 深度研究

两条线共用同一份原始资料与同一个项目空间，但解决的问题不同：RAG 解决「找到相关片段」，Wiki 解决「把知识组织成能反复使用的结构」。后者不会在每次提问时重新推导知识，而是增量维护。

## 功能

### 知识编译（Ingest）

- **两步式思维链**：第一次调用只做分析（实体、概念、主张、证据、矛盾、结构建议），第二次调用才生成文件，显著降低「边想边写」导致的遗漏与幻觉
- **严格输出协议**：`---FILE: wiki/path.md---` / `---REVIEW: type | title---` 块，解析后逐页校验 frontmatter
- **长文档分片**：按标题切分 + 重叠窗口 + 滚动全局摘要，避免超窗丢信息
- **SHA256 增量缓存**：内容未变直接跳过
- **持久化队列**：串行执行、崩溃恢复、取消、重试、逐文件进度
- **确定性降级**：未配置 LLM 时自动走抽取式编译（结构化摘要 + 高频概念页 + 具名实体页），功能可用、结果可预期

### 知识组织（Wiki）

- 目录约定：`purpose.md`（意图）/ `schema.md`（规则）/ `raw/sources`（不可变原件）/ `wiki/*`（编译产物）
- 每个页面带 YAML frontmatter：`type`、`title`、`tags`、`related`、`sources`、`created`、`updated`
- `[[wikilink]]` 交叉引用；`index.md` 自动按类型重建；`log.md` 记录每次操作；`overview.md` 每次编译后重新生成
- 页面类型：实体、概念、来源摘要、问题、对比、综合，研究模板额外提供论点、方法、发现
- 删除原始资料时级联清理：摘要页、其他页的 `sources` 引用、索引与总览
- Obsidian 兼容：`wiki/` 目录可直接作为 vault 打开

### 图谱（Graph）

- 4 信号相关性模型：直接链接 ×3.0、共享来源 ×4.0、共同邻居（Adamic-Adar）×1.5、类型亲和 ×1.0
- Louvain 社区发现 + 内聚度评分，识别松散主题簇
- 图谱洞察：跨社区/跨类型的「惊人连接」、孤立页面、松散社区、桥接节点
- 画布交互：滚轮缩放、拖拽平移、拖节点手动布局、双击打开页面
- 任一缺口可一键发起深度研究

### 检索与问答（Query）

- 分词命中（中文 bigram/分词 + 英文词干化）+ 标题加权 + 图扩展（1 跳衰减）
- 上下文预算：默认 32K tokens，按 60% 页面 / 20% 历史 / 5% 索引 / 15% 系统提示分配
- 编号上下文 + 强制 `[n]` 引用，回答可点回具体页面
- 多会话持久化、引用面板、答案回存为问题页

### 深度研究（Deep Research）

- 主题先改写成 3–5 条可检索的检索式（不同侧面：现状/证据/方法/反例）
- 多路检索：Tavily / SerpAPI / SearXNG / DuckDuckGo（无需 Key）
- 抓取网页正文（trafilatura 抽取，不截断摘要），综合成带引用的研究页
- 可选把网页原文存入 `raw/sources` 并自动编译，形成「研究 → 资料 → 知识」闭环
- 检索服务不可用时明确报错并给出配置指引，不编造

### 质检与审阅（Lint / Review）

- 质检规则：frontmatter、类型与目录一致性、来源缺失、断链、孤立页、索引未收录、日期倒挂、内容过薄
- 审阅项由编译阶段产生：矛盾、疑似重复、缺页、研究建议；预生成检索式，一键建立页面或深度研究
- 审阅不阻塞编译，可批量跳过

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | React 19 + TypeScript + Vite（无 UI 框架依赖，自绘 Markdown / 图谱画布） |
| 后端 | FastAPI + SQLite + 文件系统（wiki 工作区） |
| 检索 | Chroma / SQLite 向量 + BM25 + 图谱扩展（jieba / rank-bm25） |
| 解析 | PyMuPDF、python-docx、python-pptx、openpyxl、trafilatura |
| LLM | 任意 OpenAI 兼容端点（OpenAI / DeepSeek / Ollama / vLLM / 自建网关） |

## 快速开始

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # 至少确认为 LLM_PROVIDER / SEARCH_PROVIDER
python run.py             # http://127.0.0.1:8000  （Swagger: /docs）

# 前端（开发）
cd frontend
npm install
npm run dev               # http://127.0.0.1:8000，/api 代理到 8001
```

> 后端默认端口见 `backend/.env` 的 `APP_PORT`；前端开发代理默认指向 `8001`，按需调整 `frontend/vite.config.ts`。

生产模式由 FastAPI 同源托管 `frontend/dist`：

```bash
cd frontend && npm run build
cd ../backend && python run.py
```

## 使用路径

1. 在「知识上传」导入资料，或在「深度思考与研究 → 来源」直接上传
2. 首次进入「深度思考与研究」会要求初始化工作区，选择模板（研究型 / 阅读型 / 业务型 / 通用型）
3. 「来源」里点「全部编译」，观察队列进度
4. 「知识页」阅读编译结果，`[[wikilink]]` 可跳转，页面底部有强关联与被引用
5. 「图谱」看主题簇与知识缺口，缺口可一键研究
6. 「研究」发起深度研究，结果自动写入 `wiki/queries/`
7. 「审阅」处理矛盾与缺页，「问答」基于页面提问并回存结论

## 目录结构（单个项目工作区）

```
data/wiki/<project_id>/
├── purpose.md              # 研究意图：为什么存在、要回答什么
├── schema.md               # 页面类型、命名、frontmatter 规则
├── raw/
│   ├── sources/            # 不可变原始资料
│   └── assets/
├── wiki/
│   ├── index.md            # 内容目录（自动生成）
│   ├── log.md              # 操作日志（自动追加）
│   ├── overview.md         # 全局总览（自动生成）
│   ├── entities/           # 实体
│   ├── concepts/           # 概念
│   ├── sources/            # 来源摘要
│   ├── queries/            # 问题与研究结论
│   ├── comparisons/        # 对比
│   └── synthesis/          # 综合
└── .llm-wiki/
    ├── ingest-cache.json   # SHA256 增量缓存
    ├── queue.json          # 持久化编译队列
    ├── review.json         # 审阅项
    ├── research.json       # 深度研究任务
    ├── vectors.json        # 页面向量（可选）
    ├── settings.json       # 项目级设置
    └── chats/              # 会话记录
```

## API

统一前缀 `/api/wiki`，项目通过 `?project=<id>` 指定。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/projects` | 项目列表 + 工作区规模 |
| POST | `/projects/{id}/init` | 初始化工作区（选模板） |
| GET | `/overview` | 总览、计数、队列、环境状态 |
| GET/PUT | `/purpose`、`/schema` | 意图层与规则层读写 |
| GET/POST/DELETE | `/sources` | 来源列表 / 上传 / 删除（级联） |
| POST | `/sources/import` | 导入知识库已解析文档 |
| POST | `/ingest` | 入队编译（可指定路径、可强制重编译） |
| GET | `/queue` · POST `/queue/{id}/cancel` `/retry` | 队列控制 |
| GET | `/pages`、`/page` · POST `/page` · DELETE `/page` | 页面读写 |
| GET | `/graph`、`/insights`、`/related` | 图谱、洞察、邻居 |
| POST | `/search` | 混合检索 + 编号上下文 |
| POST | `/chat` · GET/POST `/sessions` · POST `/chat/save` | 问答与会话 |
| GET/POST | `/research`、`/research/{id}` | 深度研究 |
| GET | `/lint` · GET/POST `/reviews` | 质检与审阅 |
| GET | `/export` · POST `/import` | 项目归档迁移 |

## 配置要点

| 变量 | 作用 | 建议 |
| --- | --- | --- |
| `LLM_PROVIDER` | `none` 时走确定性编译 | 生产填 `openai`（兼容任意 OpenAI 协议端点） |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 模型接入 | `LLM_BASE_URL` 指向自建网关可避免域名问题 |
| `SEARCH_PROVIDER` | `auto`/`duckduckgo`/`tavily`/`serpapi`/`searxng` | 生产用 `tavily`，内网用 `searxng` |
| `EMBEDDING_PROVIDER` | `local`/`openai`/`hash` | 离线环境可用 `hash` 兜底 |
| `WIKI_ENABLED` | 是否启动编译队列 worker | 默认 `true` |

## 设计取舍

- **文件即真相**：wiki 是 markdown + 目录，可被 Obsidian、git 直接管理；数据库只存 RAG 的切片与向量
- **确定性优先**：索引、总览、社区编号都由程序生成，不交给模型写，避免大库被一次生成改写坏
- **降级可用**：没有 LLM / 没有检索服务时，功能明确降级并说明原因，而不是沉默或编造
- **可解释检索**：每条结果都带「命中词 / 共享来源 / 共同邻居 / 图扩展」等理由

## 运行与验证备注

- **生产构建要在 WSL 内做**：`frontend/node_modules` 是 linux-x64 二进制（`@esbuild/linux-x64`、`@rollup/rollup-linux-x64-*`），在 Windows 侧执行 `vite build` 会报 rollup 平台包缺失。改完前端后在 WSL 里 `cd frontend && npm run build`，后端才会托管新的 `dist`。
- **后端重启才会加载 wiki 模块**：`/api/wiki/*` 由 `app/wiki/api.py` 提供，旧的 uvicorn 进程不会热更新；重启后访问 `/api/wiki/templates` 能返回四套模板即说明生效。
- **升级到新代码后先跑一遍冒烟路径**：初始化 → 上传一份 md → 队列跑完 → 图谱/检索/问答，能覆盖编译、索引、图谱、检索四条主链路。


