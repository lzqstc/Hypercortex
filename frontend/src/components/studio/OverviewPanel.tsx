import { useEffect, useMemo, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type QueueTask, type WikiOverview } from './wikiApi'
import { EmptyState, Meter, PanelHead, STATUS_LABELS, Tag, formatTime } from './ui'

interface Props {
  projectId: string
  overview: WikiOverview | null
  loading: boolean
  onRefresh: () => void
  onNavigate: (tab: string) => void
  onInit: (template: string) => void
  templates: { id: string; name: string; description: string; icon: string }[]
  queue: QueueTask[]
}

const STEPS = ['导入资料', '两步编译', '审阅补漏', '图谱连接', '研究缺口']

const OverviewPanel = ({
  projectId,
  overview,
  loading,
  onRefresh,
  onNavigate,
  onInit,
  templates,
  queue,
}: Props) => {
  const { track } = useFeedback()
  const [purpose, setPurpose] = useState('')
  const [template, setTemplate] = useState('research')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    setPurpose(overview?.purpose || '')
  }, [overview?.purpose])

  const running = queue.filter((task) => task.status === 'running')
  const pending = queue.filter((task) => task.status === 'queued')
  const failed = queue.filter((task) => task.status === 'error')
  const done = queue.filter((task) => task.status === 'done').slice(0, 4)

  const counts = overview?.counts
  const exists = overview?.project.exists ?? false

  const stats = useMemo(
    () => [
      { key: 'sources', label: '原始资料', value: counts?.sources ?? 0, hint: '不可变原件', tab: 'sources', tone: 'indigo' },
      { key: 'pages', label: '知识页面', value: counts?.pages ?? 0, hint: '可追溯编译产物', tab: 'pages', tone: 'violet' },
      { key: 'reviews', label: '待审阅', value: counts?.reviews ?? 0, hint: '需要人工判断', tab: 'reviews', tone: 'amber' },
      {
        key: 'lint',
        label: '质检问题',
        value: (counts?.lintErrors ?? 0) + (counts?.lintWarnings ?? 0),
        hint: `${counts?.lintErrors ?? 0} 错误 · ${counts?.lintWarnings ?? 0} 警告`,
        tab: 'lint',
        tone: 'rose',
      },
    ],
    [counts],
  )

  const run = async (key: string, task: () => Promise<unknown>, message: string) => {
    setBusy(key)
    const result = await track(task, { loading: message, success: `${message.replace('正在', '')}完成`, error: '操作失败' })
    setBusy('')
    if (result) onRefresh()
  }

  if (!exists && !loading) {
    return (
      <div className="hc-studio__panel">
        <PanelHead title="知识编译引擎" hint="LLM Wiki 工作流：原始资料 → 结构化知识 → 可溯源结论" />
        <div className="hc-studio__init">
          <p className="hc-studio__init-lead">
            当前项目还没有 Wiki 工作区。初始化后会得到 <code>purpose.md</code>（研究意图）、
            <code>schema.md</code>（页面规则）与 <code>raw/sources</code>（不可变原件）三层结构。
          </p>
          <div className="hc-studio__templates">
            {templates.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`hc-studio__template${template === item.id ? ' is-active' : ''}`}
                onClick={() => setTemplate(item.id)}
              >
                <span className="hc-studio__template-icon">{item.icon}</span>
                <span className="hc-studio__template-name">{item.name}</span>
                <span className="hc-studio__template-desc">{item.description}</span>
              </button>
            ))}
          </div>
          <button
            type="button"
            className="hc-studio__btn is-primary"
            disabled={busy === 'init'}
            onClick={() => onInit(template)}
          >
            {busy === 'init' ? '初始化中…' : '初始化工作区'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="hc-studio__panel">
      <PanelHead
        title="研究总览"
        hint={overview ? `${overview.project.name} · 健康度 ${Math.round((overview.health || 0) * 100)}%` : '读取中…'}
        actions={
          <>
            <button type="button" className="hc-studio__btn" onClick={onRefresh} disabled={loading}>
              刷新
            </button>
            <button
              type="button"
              className="hc-studio__btn is-primary"
              disabled={busy === 'ingest'}
              onClick={() =>
                void run('ingest', () => wikiApi.ingest(projectId), '正在编译全部资料')
              }
            >
              {busy === 'ingest' ? '编译中…' : '全部编译'}
            </button>
          </>
        }
      />

      <div className="hc-studio__stats">
        {stats.map((stat) => (
          <button
            key={stat.key}
            type="button"
            className={`hc-studio__stat is-${stat.tone}`}
            onClick={() => onNavigate(stat.tab)}
          >
            <span className="hc-studio__stat-label">{stat.label}</span>
            <strong>{stat.value}</strong>
            <span className="hc-studio__stat-hint">{stat.hint}</span>
          </button>
        ))}
      </div>

      <div className="hc-studio__flow">
        {STEPS.map((step, index) => {
          const active =
            (index === 0 && (counts?.sources ?? 0) > 0) ||
            (index === 1 && (counts?.pages ?? 0) > 0) ||
            (index === 2 && (counts?.reviews ?? 0) === 0 && (counts?.pages ?? 0) > 0) ||
            (index === 3 && (overview?.byType?.length ?? 0) > 2) ||
            (index === 4 && (counts?.pages ?? 0) > 6)
          return (
            <div key={step} className={`hc-studio__flow-step${active ? ' is-active' : ''}`}>
              <span className="hc-studio__flow-index">{index + 1}</span>
              <span>{step}</span>
            </div>
          )
        })}
      </div>

      <div className="hc-studio__grid">
        <section className="hc-studio__card">
          <header className="hc-studio__card-head">
            <h3>编译队列</h3>
            <span className="hc-studio__muted">
              {running.length ? `${running.length} 个进行中` : pending.length ? `${pending.length} 个待处理` : '空闲'}
            </span>
          </header>
          {queue.length === 0 ? (
            <p className="hc-studio__muted hc-studio__card-empty">还没有编译任务。导入资料后会自动排队。</p>
          ) : (
            <ul className="hc-studio__queue">
              {queue.slice(0, 8).map((task) => (
                <li key={task.id} className={`hc-studio__queue-item is-${task.status}`}>
                  <div className="hc-studio__queue-main">
                    <span className="hc-studio__queue-name" title={task.sourceName}>
                      {task.sourceName}
                    </span>
                    <span className="hc-studio__queue-stage">
                      {task.stage || STATUS_LABELS[task.status]}
                      {task.error ? ` · ${task.error}` : ''}
                    </span>
                  </div>
                  <div className="hc-studio__queue-side">
                    <Tag tone={task.status === 'error' ? 'rose' : task.status === 'done' ? 'green' : 'slate'}>
                      {STATUS_LABELS[task.status] || task.status}
                    </Tag>
                    {task.status === 'error' || task.status === 'cancelled' ? (
                      <button
                        type="button"
                        className="hc-studio__link"
                        onClick={() => void run(`retry-${task.id}`, () => wikiApi.retry(projectId, task.id), '正在重试')}
                      >
                        重试
                      </button>
                    ) : null}
                    {task.status === 'running' || task.status === 'queued' ? (
                      <button
                        type="button"
                        className="hc-studio__link"
                        onClick={() => void run(`cancel-${task.id}`, () => wikiApi.cancel(projectId, task.id), '正在取消')}
                      >
                        取消
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="hc-studio__card">
          <header className="hc-studio__card-head">
            <h3>研究意图 purpose.md</h3>
            <span className="hc-studio__muted">每次编译与提问都会读取</span>
          </header>
          <textarea
            className="hc-studio__textarea"
            value={purpose}
            rows={9}
            onChange={(event) => setPurpose(event.target.value)}
            placeholder="这个知识库为什么存在？要回答哪些核心问题？范围与质量底线是什么？"
          />
          <div className="hc-studio__card-actions">
            <button
              type="button"
              className="hc-studio__btn is-ghost"
              onClick={() => onNavigate('pages')}
            >
              查看页面
            </button>
            <button
              type="button"
              className="hc-studio__btn is-primary"
              disabled={busy === 'purpose' || purpose === (overview?.purpose || '')}
              onClick={() => void run('purpose', () => wikiApi.purpose.set(projectId, purpose), '正在保存意图')}
            >
              保存意图
            </button>
          </div>
        </section>

        <section className="hc-studio__card">
          <header className="hc-studio__card-head">
            <h3>运行环境</h3>
            <span className="hc-studio__muted">能力雷达</span>
          </header>
          <ul className="hc-studio__env">
            <li>
              <span>LLM 编译</span>
              <Tag tone={overview?.llm.available ? 'green' : 'amber'}>
                {overview?.llm.available ? overview.llm.model || '已配置' : '未配置 · 走确定性编译'}
              </Tag>
            </li>
            <li>
              <span>向量检索</span>
              <Tag tone={overview?.settings?.vectorSearch ? 'green' : 'slate'}>
                {overview?.settings?.vectorSearch ? '开启' : '关闭'}
              </Tag>
            </li>
            <li>
              <span>上下文预算</span>
              <Tag tone="slate">{String(overview?.settings?.contextTokens ?? 32000)} tokens</Tag>
            </li>
            <li>
              <span>图谱规模</span>
              <Tag tone="violet">{overview?.byType.reduce((sum, item) => sum + item.count, 0) ?? 0} 节点</Tag>
            </li>
          </ul>
          {!overview?.llm.available ? (
            <p className="hc-studio__hint">
              未配置 LLM 时使用确定性编译：抽取式摘要 + 高频概念页，功能可用但缺少判断与矛盾检测。
              在 <code>backend/.env</code> 设置 <code>LLM_PROVIDER=openai</code> 与 <code>LLM_API_KEY</code> 后重新编译即可升级。
            </p>
          ) : null}
        </section>

        <section className="hc-studio__card">
          <header className="hc-studio__card-head">
            <h3>维护动作</h3>
            <span className="hc-studio__muted">可重复执行</span>
          </header>
          <div className="hc-studio__actions">
            <button
              type="button"
              className="hc-studio__action"
              onClick={() =>
                void run('import', () => wikiApi.sources.importDocuments(projectId), '正在导入已解析文档')
              }
            >
              <strong>导入知识库文档</strong>
              <span>把「知识上传」里已解析的文件复制为原始资料</span>
            </button>
            <button
              type="button"
              className="hc-studio__action"
              onClick={() => void run('rebuild', () => wikiApi.rebuild(projectId), '正在重建索引')}
            >
              <strong>重建索引与总览</strong>
              <span>index.md / overview.md 由系统确定性生成</span>
            </button>
            <button
              type="button"
              className="hc-studio__action"
              onClick={() => window.open(wikiApi.exportUrl(projectId), '_blank')}
            >
              <strong>导出项目归档</strong>
              <span>zip 包含 wiki / raw / 配置，可跨设备迁移</span>
            </button>
            <button
              type="button"
              className="hc-studio__action is-danger"
              onClick={() => {
                if (!window.confirm('清空所有 wiki 页面（保留原始资料）？此操作不可撤销。')) return
                void run('reset', () => wikiApi.reset(projectId), '正在清空页面')
              }}
            >
              <strong>清空知识页</strong>
              <span>保留 raw/sources，重新编译可恢复</span>
            </button>
          </div>
        </section>
      </div>

      {done.length ? (
        <div className="hc-studio__recent">
          <span className="hc-studio__muted">最近完成</span>
          {done.map((task) => (
            <span key={task.id} className="hc-studio__recent-item" title={task.pagesWritten.join(', ')}>
              ✓ {task.sourceName} · {formatTime(task.updatedAt)} · {task.pagesWritten.length} 页
            </span>
          ))}
        </div>
      ) : null}

      {failed.length ? (
        <div className="hc-studio__banner is-rose">
          {failed.length} 个编译任务失败：{failed[0].sourceName} — {failed[0].error || '未知错误'}
        </div>
      ) : null}

      {overview ? (
        <div className="hc-studio__meter-row">
          <span>页面健康度</span>
          <Meter value={overview.health} tone="green" />
          <span className="hc-studio__muted">{Math.round(overview.health * 100)}%</span>
        </div>
      ) : null}

      {loading ? <EmptyState title="正在读取工作区…" /> : null}
    </div>
  )
}

export default OverviewPanel
