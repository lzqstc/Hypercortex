import { useCallback, useEffect, useRef, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type ResearchTask } from './wikiApi'
import { EmptyState, PanelHead, Tag, formatTime } from './ui'
import Markdown from './Markdown'

interface Props {
  projectId: string
  initialTopic: string
  tasks: ResearchTask[]
  onOpenPage: (path: string) => void
  onRefresh: () => void
}

const EXAMPLES = [
  '低空经济中，空域管理与基础设施之间的瓶颈关系是什么？',
  '大模型在知识库场景下的幻觉来源有哪些实证证据？',
  '这个项目的定价策略里，哪些假设还没有数据支撑？',
]

const STEP_ICON: Record<string, string> = { done: '✓', running: '◐', pending: '○', error: '×' }

const ResearchPanel = ({ projectId, initialTopic, tasks, onOpenPage, onRefresh }: Props) => {
  const { notify, track } = useFeedback()
  const [topic, setTopic] = useState('')
  const [autoIngest, setAutoIngest] = useState(true)
  const [current, setCurrent] = useState<ResearchTask | null>(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (initialTopic) setTopic(initialTopic)
  }, [initialTopic])

  useEffect(() => {
    if (!current || current.status !== 'running') return
    timer.current = window.setInterval(async () => {
      try {
        const data = await wikiApi.research.get(projectId, current.id)
        setCurrent(data.item)
        if (data.item.status !== 'running') {
          if (timer.current) window.clearInterval(timer.current)
          onRefresh()
          if (data.item.status === 'completed') notify('研究完成，已写入研究页', 'success')
        }
      } catch {
        if (timer.current) window.clearInterval(timer.current)
      }
    }, 1600)
    return () => {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [current, projectId, notify, onRefresh])

  useEffect(() => {
    if (!current && tasks.length) setCurrent(tasks[0])
  }, [tasks, current])

  const start = useCallback(async () => {
    const value = topic.trim()
    if (value.length < 2) {
      notify('请输入更具体的研究主题', 'error')
      return
    }
    setBusy(true)
    const created = await track(() => wikiApi.research.start(projectId, value, { autoIngest }), {
      loading: '正在规划检索式并启动研究',
      error: '启动失败',
    })
    setBusy(false)
    if (created?.item) {
      setCurrent(created.item)
      onRefresh()
    }
  }, [topic, projectId, autoIngest, track, notify, onRefresh])

  const sources = current?.sources || []

  return (
    <div className="hc-studio__panel hc-studio__panel--research">
      <PanelHead
        title="深度研究"
        hint="主题改写 → 多路检索 → 正文抽取 → 综合成页 → 自动归档，全程可追溯"
        actions={
          current ? (
            <span className="hc-studio__muted">最近：{formatTime(current.updatedAt)}</span>
          ) : null
        }
      />

      <div className="hc-studio__research-form">
        <textarea
          className="hc-studio__textarea"
          rows={3}
          placeholder="描述要研究的问题：越具体越好，包含对象、时间范围、争议点"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
              event.preventDefault()
              void start()
            }
          }}
        />
        <div className="hc-studio__research-controls">
          <label className="hc-studio__check">
            <input type="checkbox" checked={autoIngest} onChange={(event) => setAutoIngest(event.target.checked)} />
            把抓取到的网页存入原始资料并自动编译
          </label>
          <span className="hc-studio__muted">Ctrl / ⌘ + Enter 开始</span>
          <button type="button" className="hc-studio__btn is-primary" onClick={() => void start()} disabled={busy}>
            {busy ? '启动中…' : '开始研究'}
          </button>
        </div>
        {!topic ? (
          <div className="hc-studio__chips">
            {EXAMPLES.map((example) => (
              <button key={example} type="button" className="hc-studio__chip" onClick={() => setTopic(example)}>
                {example}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="hc-studio__research-body">
        <section className="hc-studio__research-main">
          {!current ? (
            <EmptyState
              title="还没有研究任务"
              hint="研究会在公开网络上取证并写成页面；如果你的环境没有配置检索服务，会明确提示而不是编造。"
            />
          ) : (
            <>
              <div className="hc-studio__research-head">
                <div>
                  <h3>{current.topic}</h3>
                  <div className="hc-studio__row-meta">
                    {current.queries.length} 条检索式 · {sources.length} 篇材料 · {current.archivedSources?.length || 0} 份已归档
                  </div>
                </div>
                <Tag tone={current.status === 'completed' ? 'green' : current.status === 'error' ? 'rose' : 'indigo'}>
                  {current.status === 'completed' ? '已完成' : current.status === 'error' ? '失败' : current.stage}
                </Tag>
              </div>

              <div className="hc-studio__steps">
                {current.steps.map((step) => (
                  <div key={step.key} className={`hc-studio__step is-${step.status}`}>
                    <span className="hc-studio__step-mark">{STEP_ICON[step.status] || '○'}</span>
                    {step.label}
                  </div>
                ))}
              </div>

              <div className="hc-studio__progress">
                <span style={{ width: `${Math.min(100, Math.max(4, current.progress))}%` }} />
              </div>

              {current.error ? (
                <div className="hc-studio__banner is-rose">
                  {current.error}
                  <p className="hc-studio__muted">
                    可在 <code>backend/.env</code> 配置 <code>SEARCH_PROVIDER=tavily</code> 与
                    <code>TAVILY_API_KEY</code>（或 serpapi / searxng）后重试。
                  </p>
                </div>
              ) : null}

              {current.queries.length ? (
                <div className="hc-studio__queries">
                  {current.queries.map((query) => (
                    <span key={query} className="hc-studio__query">
                      {query}
                    </span>
                  ))}
                </div>
              ) : null}

              {current.content ? (
                <article className="hc-studio__research-content">
                  <Markdown content={current.content} onExternal={(url) => window.open(url, '_blank')} />
                </article>
              ) : null}

              {sources.length ? (
                <div className="hc-studio__sources-mini">
                  <span className="hc-studio__muted">材料</span>
                  <ol>
                    {sources.map((source) => (
                      <li key={`${source.index}-${source.url}`}>
                        <button type="button" className="hc-studio__link" onClick={() => window.open(source.url, '_blank')}>
                          {source.title || source.url}
                        </button>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}

              {current.gaps.length ? (
                <div className="hc-studio__gaps-inline">
                  <span className="hc-studio__muted">知识缺口</span>
                  <ul>
                    {current.gaps.map((gap) => (
                      <li key={gap}>{gap}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {current.pagePath ? (
                <div className="hc-studio__card-actions">
                  <button type="button" className="hc-studio__btn is-primary" onClick={() => onOpenPage(current.pagePath)}>
                    打开研究页
                  </button>
                  <button
                    type="button"
                    className="hc-studio__btn is-ghost"
                    onClick={() => setTopic(`${current.topic}（补充反例与量化证据）`)}
                  >
                    继续追问
                  </button>
                </div>
              ) : null}
            </>
          )}
        </section>

        <aside className="hc-studio__research-side">
          <header className="hc-studio__side-head">
            <strong>研究记录</strong>
            <span className="hc-studio__muted">{tasks.length}</span>
          </header>
          {tasks.length === 0 ? (
            <p className="hc-studio__muted hc-studio__card-empty">还没有记录。</p>
          ) : (
            <ul className="hc-studio__history">
              {tasks.map((task) => (
                <li key={task.id}>
                  <button
                    type="button"
                    className={`hc-studio__history-item${current?.id === task.id ? ' is-active' : ''}`}
                    onClick={() => setCurrent(task)}
                  >
                    <span>{task.topic}</span>
                    <em>
                      {task.status === 'completed' ? '完成' : task.status === 'error' ? '失败' : '进行中'} ·{' '}
                      {formatTime(task.updatedAt)}
                    </em>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  )
}

export default ResearchPanel
