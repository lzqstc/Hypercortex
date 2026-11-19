import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type LintResult, type PageSummary, type QueueTask, type ResearchTask, type ReviewItem, type SourceItem, type WikiOverview } from './wikiApi'
import OverviewPanel from './OverviewPanel'
import PagesPanel from './PagesPanel'
import SourcesPanel from './SourcesPanel'
import GraphPanel from './GraphPanel'
import SearchPanel from './SearchPanel'
import ResearchPanel from './ResearchPanel'
import ChatPanel from './ChatPanel'
import ReviewPanel from './ReviewPanel'
import { Spinner, Tag } from './ui'
import '@/styles/studio.css'

interface Props {
  projectId?: string
}

const TABS = [
  { key: 'overview', label: '总览', icon: '◍' },
  { key: 'pages', label: '知识页', icon: '▤' },
  { key: 'sources', label: '来源', icon: '⬗' },
  { key: 'graph', label: '图谱', icon: '◈' },
  { key: 'search', label: '检索', icon: '⌕' },
  { key: 'research', label: '研究', icon: '✦' },
  { key: 'chat', label: '问答', icon: '◌' },
  { key: 'reviews', label: '审阅', icon: '✓' },
]

const KnowledgeStudio = ({ projectId = 'default' }: Props) => {
  const { notify } = useFeedback()
  const [tab, setTab] = useState('overview')
  const [overview, setOverview] = useState<WikiOverview | null>(null)
  const [pages, setPages] = useState<PageSummary[]>([])
  const [pageTypes, setPageTypes] = useState<{ type: string; label: string; count: number }[]>([])
  const [sources, setSources] = useState<SourceItem[]>([])
  const [reviews, setReviews] = useState<ReviewItem[]>([])
  const [lint, setLint] = useState<LintResult | null>(null)
  const [tasks, setTasks] = useState<ResearchTask[]>([])
  const [templates, setTemplates] = useState<{ id: string; name: string; description: string; icon: string }[]>([])
  const [selectedPage, setSelectedPage] = useState('')
  const [researchTopic, setResearchTopic] = useState('')
  const [loading, setLoading] = useState(true)
  const [graphKey, setGraphKey] = useState(0)
  const pollRef = useRef<number | null>(null)

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true)
      try {
        const [overviewData, pageData, sourceData, reviewData, lintData, researchData] = await Promise.all([
          wikiApi.overview(projectId),
          wikiApi.pages.list(projectId).catch(() => ({ items: [], types: [] })),
          wikiApi.sources.list(projectId).catch(() => ({ project: { id: projectId, name: '', exists: false }, items: [] })),
          wikiApi.reviews.list(projectId).catch(() => ({ items: [], total: 0 })),
          wikiApi.lint(projectId).catch(() => null),
          wikiApi.research.list(projectId).catch(() => ({ items: [] })),
        ])
        setOverview(overviewData)
        setPages(pageData.items)
        setPageTypes(pageData.types)
        setSources(sourceData.items)
        setReviews(reviewData.items)
        setLint(lintData)
        setTasks(researchData.items)
        setGraphKey((value) => value + 1)
      } catch (error) {
        notify(error instanceof Error ? error.message : '读取工作区失败', 'error')
        setOverview(null)
      } finally {
        setLoading(false)
      }
    },
    [projectId, notify],
  )

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    wikiApi
      .templates()
      .then((data) => setTemplates(data.items))
      .catch(() => setTemplates([]))
  }, [])

  const queue = overview?.queue || []
  const activeQueue = useMemo(
    () => queue.filter((task) => task.status === 'queued' || task.status === 'running'),
    [queue],
  )

  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (!activeQueue.length) return
    pollRef.current = window.setInterval(() => {
      void load(true)
    }, 2500)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [activeQueue.length, load])

  const init = async (template: string) => {
    try {
      await wikiApi.init(projectId, template)
      notify('工作区已初始化', 'success')
      await load()
      setTab('sources')
    } catch (error) {
      notify(error instanceof Error ? error.message : '初始化失败', 'error')
    }
  }

  const openPage = useCallback((path: string) => {
    setSelectedPage(path)
    setTab('pages')
  }, [])

  const openResearch = useCallback((topic: string) => {
    setResearchTopic(topic)
    setTab('research')
  }, [])

  const queuePill = activeQueue.length ? (
    <span className="hc-studio__pill is-running">
      <span className="hc-studio__pill-dot" />
      {activeQueue[0].stage || '编译中'} · {activeQueue[0].sourceName.slice(0, 18)}
    </span>
  ) : (
    <span className="hc-studio__pill is-idle">
      {overview?.counts.queue ? `${overview.counts.queue} 个待处理` : '队列空闲'}
    </span>
  )

  return (
    <section className="hc-studio" aria-label="深度思考与研究">
      <header className="hc-studio__top">
        <div className="hc-studio__brand">
          <span className="hc-studio__brand-mark" aria-hidden="true" />
          <div>
            <h1>深度思考与研究</h1>
            <p>LLM Wiki · 资料编译为知识 · 结论可溯源</p>
          </div>
        </div>
        <div className="hc-studio__top-meta">
          {overview ? (
            <>
              <span className="hc-studio__project">{overview.project.name}</span>
              <Tag tone={overview.llm.available ? 'green' : 'amber'}>
                {overview.llm.available ? `LLM · ${overview.llm.model}` : '确定性编译'}
              </Tag>
              <Tag tone="slate">
                健康 {Math.round((overview.health || 0) * 100)}%
              </Tag>
            </>
          ) : (
            <Spinner label="读取中" />
          )}
          {queuePill}
        </div>
      </header>

      <nav className="hc-studio__tabs">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`hc-studio__tab${tab === item.key ? ' is-active' : ''}`}
            onClick={() => setTab(item.key)}
          >
            <span className="hc-studio__tab-icon" aria-hidden="true">
              {item.icon}
            </span>
            {item.label}
            {item.key === 'reviews' && reviews.length ? <em>{reviews.length}</em> : null}
            {item.key === 'pages' && pages.length ? <em>{pages.length}</em> : null}
          </button>
        ))}
        <span className="hc-studio__tabs-spacer" />
        <button type="button" className="hc-studio__tab is-ghost" onClick={() => void load()} disabled={loading}>
          {loading ? '同步中…' : '同步'}
        </button>
      </nav>

      <div className="hc-studio__body">
        {tab === 'overview' ? (
          <OverviewPanel
            projectId={projectId}
            overview={overview}
            loading={loading}
            onRefresh={() => void load()}
            onNavigate={setTab}
            onInit={(template) => void init(template)}
            templates={templates}
            queue={queue as QueueTask[]}
          />
        ) : null}

        {tab === 'pages' ? (
          <PagesPanel
            projectId={projectId}
            pages={pages}
            types={pageTypes}
            selected={selectedPage}
            loading={loading}
            onSelect={setSelectedPage}
            onRefresh={() => void load()}
            onExternal={(url) => window.open(url, '_blank')}
          />
        ) : null}

        {tab === 'sources' ? (
          <SourcesPanel
            projectId={projectId}
            sources={sources}
            loading={loading}
            onRefresh={() => void load()}
            onOpenPage={openPage}
          />
        ) : null}

        {tab === 'graph' ? (
          <GraphPanel projectId={projectId} onOpenPage={openPage} onResearch={openResearch} refreshKey={graphKey} />
        ) : null}

        {tab === 'search' ? <SearchPanel projectId={projectId} onOpenPage={openPage} /> : null}

        {tab === 'research' ? (
          <ResearchPanel
            projectId={projectId}
            initialTopic={researchTopic}
            tasks={tasks}
            onOpenPage={openPage}
            onRefresh={() => void load()}
          />
        ) : null}

        {tab === 'chat' ? <ChatPanel projectId={projectId} onOpenPage={openPage} /> : null}

        {tab === 'reviews' ? (
          <ReviewPanel
            projectId={projectId}
            lint={lint}
            reviews={reviews}
            loading={loading}
            onRefresh={() => void load()}
            onOpenPage={openPage}
            onResearch={openResearch}
          />
        ) : null}
      </div>
    </section>
  )
}

export default KnowledgeStudio
