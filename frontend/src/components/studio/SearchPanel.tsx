import { useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type SearchResult } from './wikiApi'
import { EmptyState, PanelHead, Tag, shortPath, typeLabel } from './ui'

interface Props {
  projectId: string
  onOpenPage: (path: string) => void
}

const SearchPanel = ({ projectId, onOpenPage }: Props) => {
  const { notify } = useFeedback()
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [includeSources, setIncludeSources] = useState(true)
  const [expand, setExpand] = useState(true)
  const [showContext, setShowContext] = useState(false)

  const run = async () => {
    const value = query.trim()
    if (!value) {
      notify('请输入检索内容', 'error')
      return
    }
    setLoading(true)
    try {
      const data = await wikiApi.search(projectId, value, { includeSources, expand, limit: 12 })
      setResult(data)
    } catch (error) {
      notify(error instanceof Error ? error.message : '检索失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="hc-studio__panel">
      <PanelHead
        title="混合检索"
        hint="分词命中 + 图谱扩展 + 编号上下文；结果可直接作为模型依据"
        actions={
          result ? (
            <button type="button" className="hc-studio__btn is-ghost" onClick={() => setShowContext((value) => !value)}>
              {showContext ? '隐藏上下文' : '查看上下文'}
            </button>
          ) : null
        }
      />

      <div className="hc-studio__searchbar">
        <input
          className="hc-studio__input is-large"
          placeholder="问一个具体问题，或输入关键词：例如「低空经济 空域管理 瓶颈」"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void run()
          }}
        />
        <button type="button" className="hc-studio__btn is-primary" onClick={() => void run()} disabled={loading}>
          {loading ? '检索中…' : '检索'}
        </button>
      </div>

      <div className="hc-studio__tools">
        <label className="hc-studio__check">
          <input type="checkbox" checked={includeSources} onChange={(event) => setIncludeSources(event.target.checked)} />
          检索原始资料
        </label>
        <label className="hc-studio__check">
          <input type="checkbox" checked={expand} onChange={(event) => setExpand(event.target.checked)} />
          图谱扩展（带出强关联页）
        </label>
        {result ? (
          <span className="hc-studio__muted">
            预算 {result.budget.tokens} tokens · 页面配额 {result.budget.pages} 字符
          </span>
        ) : null}
      </div>

      {!result ? (
        <EmptyState
          title="检索会返回「可核验」的证据"
          hint="每个结果都带命中原因、来源与路径；图谱扩展会说明它为什么被带进来。"
        />
      ) : result.items.length === 0 ? (
        <EmptyState title="没有命中" hint="换用更具体的词，或先在「研究」里补充外部资料。" />
      ) : (
        <>
          <ul className="hc-studio__list">
            {result.items.map((hit) => (
              <li key={`${hit.kind}-${hit.path}`} className="hc-studio__row is-hit">
                <div className="hc-studio__score">{Math.round(hit.score * 100)}</div>
                <div className="hc-studio__row-main">
                  <div className="hc-studio__row-title">
                    {hit.title}
                    <Tag tone={hit.kind === 'related' ? 'violet' : hit.kind === 'source' ? 'green' : 'indigo'}>
                      {hit.kind === 'related' ? '图扩展' : hit.kind === 'source' ? '原件' : typeLabel(hit.type)}
                    </Tag>
                  </div>
                  <p className="hc-studio__snippet">{hit.snippet}</p>
                  <div className="hc-studio__row-meta">
                    {shortPath(hit.path)} · {hit.reasons.join(' · ')}
                  </div>
                </div>
                <div className="hc-studio__row-actions">
                  {hit.kind !== 'source' ? (
                    <button type="button" className="hc-studio__link" onClick={() => onOpenPage(hit.path)}>
                      打开
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>

          {showContext ? (
            <div className="hc-studio__context">
              <header>
                <strong>装配后的编号上下文</strong>
                <span className="hc-studio__muted">模型实际看到的内容（已按预算截断）</span>
              </header>
              <pre>{result.context}</pre>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}

export default SearchPanel
