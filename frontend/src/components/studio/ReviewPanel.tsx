import { useMemo, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type LintResult, type ReviewItem } from './wikiApi'
import { EmptyState, Meter, PanelHead, Tag, shortPath } from './ui'

interface Props {
  projectId: string
  lint: LintResult | null
  reviews: ReviewItem[]
  loading: boolean
  onRefresh: () => void
  onOpenPage: (path: string) => void
  onResearch: (topic: string) => void
}

const REVIEW_LABELS: Record<string, string> = {
  contradiction: '矛盾',
  duplicate: '可能重复',
  'missing-page': '缺页',
  suggestion: '建议',
}

const ReviewPanel = ({ projectId, lint, reviews, loading, onRefresh, onOpenPage, onResearch }: Props) => {
  const { notify, track } = useFeedback()
  const [busy, setBusy] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const groups = useMemo(() => {
    const map = new Map<string, { level: string; code: string; items: { file: string; message: string }[] }>()
    ;(lint?.issues || []).forEach((issue) => {
      const entry = map.get(issue.code) || { level: issue.level, code: issue.code, items: [] }
      entry.items.push({ file: issue.file, message: issue.message })
      map.set(issue.code, entry)
    })
    return [...map.entries()].sort((a, b) => (a[1].level === 'error' ? -1 : 1) - (b[1].level === 'error' ? -1 : 1))
  }, [lint])

  const act = async (key: string, action: () => Promise<unknown>, message: string) => {
    setBusy(key)
    const result = await track(action, { loading: message, success: '已处理', error: '处理失败' })
    setBusy('')
    if (result) onRefresh()
  }

  const research = async (item: ReviewItem) => {
    setBusy(`res-${item.id}`)
    const topic = item.searchQueries?.length ? `${item.title}（${item.searchQueries.slice(0, 2).join('；')}）` : item.title
    const result = await track(() => wikiApi.reviews.research(projectId, item.id), {
      loading: '正在发起深度研究',
      success: '研究任务已启动',
      error: '发起失败',
    })
    setBusy('')
    if (result) {
      onResearch(topic)
      onRefresh()
    }
  }

  return (
    <div className="hc-studio__panel">
      <PanelHead
        title="审阅与质检"
        hint="LLM 只标记需要人判断的地方，不阻塞编译；质检保证结构长期可维护"
        actions={
          <>
            {reviews.length ? (
              <button
                type="button"
                className="hc-studio__btn is-ghost"
                onClick={() =>
                  void act(
                    'batch',
                    () => wikiApi.reviews.resolveBatch(projectId, reviews.map((item) => item.id), 'Skip'),
                    '正在批量跳过',
                  )
                }
              >
                全部标记跳过
              </button>
            ) : null}
            <button type="button" className="hc-studio__btn" onClick={onRefresh} disabled={loading}>
              刷新
            </button>
          </>
        }
      />

      <div className="hc-studio__grid is-two">
        <section className="hc-studio__card">
          <header className="hc-studio__card-head">
            <h3>待审阅项</h3>
            <span className="hc-studio__muted">{reviews.length} 项</span>
          </header>
          {reviews.length === 0 ? (
            <p className="hc-studio__muted hc-studio__card-empty">队列已清空。编译新资料时会重新产生。</p>
          ) : (
            <ul className="hc-studio__reviews">
              {reviews.map((item) => (
                <li key={item.id}>
                  <div className="hc-studio__review-head">
                    <Tag
                      tone={
                        item.type === 'contradiction'
                          ? 'rose'
                          : item.type === 'duplicate'
                            ? 'amber'
                            : item.type === 'missing-page'
                              ? 'violet'
                              : 'slate'
                      }
                    >
                      {REVIEW_LABELS[item.type] || item.type}
                    </Tag>
                    <strong>{item.title}</strong>
                  </div>
                  {item.description ? <p className="hc-studio__review-desc">{item.description}</p> : null}
                  {item.affectedPages?.length ? (
                    <div className="hc-studio__row-meta">影响：{item.affectedPages.map(shortPath).join('、')}</div>
                  ) : null}
                  {item.searchQueries?.length ? (
                    <div className="hc-studio__queries">
                      {item.searchQueries.map((query) => (
                        <span key={query} className="hc-studio__query">
                          {query}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="hc-studio__review-actions">
                    <button
                      type="button"
                      className="hc-studio__btn is-ghost"
                      disabled={busy === item.id}
                      onClick={() =>
                        void act(
                          item.id,
                          async () => {
                            const result = await wikiApi.reviews.createPage(projectId, item.id)
                            if (result.path) onOpenPage(result.path)
                            return result
                          },
                          '正在建立页面',
                        )
                      }
                    >
                      建立页面
                    </button>
                    <button
                      type="button"
                      className="hc-studio__btn is-ghost"
                      disabled={busy === `res-${item.id}`}
                      onClick={() => void research(item)}
                    >
                      深度研究
                    </button>
                    <button
                      type="button"
                      className="hc-studio__link"
                      onClick={() =>
                        void act(
                          `${item.id}-skip`,
                          () => wikiApi.reviews.resolve(projectId, item.id, 'Skip'),
                          '正在标记跳过',
                        )
                      }
                    >
                      跳过
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="hc-studio__card">
          <header className="hc-studio__card-head">
            <h3>结构质检</h3>
            <span className="hc-studio__muted">
              {lint ? `${lint.stats.errors} 错误 · ${lint.stats.warnings} 警告 · ${lint.stats.pages} 页` : '读取中…'}
            </span>
          </header>
          {lint ? (
            <div className="hc-studio__meter-row">
              <span>健康度</span>
              <Meter value={lint.stats.health} tone="green" />
              <span className="hc-studio__muted">{Math.round(lint.stats.health * 100)}%</span>
            </div>
          ) : null}
          {groups.length === 0 ? (
            <p className="hc-studio__muted hc-studio__card-empty">结构检查通过。</p>
          ) : (
            <div className="hc-studio__lint-groups">
              {groups.map(([code, group]) => {
                const open = expanded[code] ?? group.level === 'error'
                return (
                  <div key={code} className="hc-studio__lint-group">
                    <button
                      type="button"
                      className="hc-studio__lint-head"
                      onClick={() => setExpanded((current) => ({ ...current, [code]: !open }))}
                    >
                      <span>{open ? '▾' : '▸'}</span>
                      <Tag tone={group.level === 'error' ? 'rose' : group.level === 'info' ? 'slate' : 'amber'}>
                        {group.level === 'error' ? '错误' : group.level === 'info' ? '提示' : '警告'}
                      </Tag>
                      <strong>{lint?.labels[code] || code}</strong>
                      <em>{group.items.length}</em>
                    </button>
                    {open ? (
                      <ul className="hc-studio__lint-list">
                        {group.items.slice(0, 12).map((issue, index) => (
                          <li key={`${issue.file}-${index}`}>
                            <span>{issue.message}</span>
                            <button type="button" className="hc-studio__link" onClick={() => onOpenPage(issue.file)}>
                              {shortPath(issue.file)}
                            </button>
                          </li>
                        ))}
                        {group.items.length > 12 ? <li className="hc-studio__muted">还有 {group.items.length - 12} 条</li> : null}
                      </ul>
                    ) : null}
                  </div>
                )
              })}
            </div>
          )}
          <div className="hc-studio__card-actions">
            <button
              type="button"
              className="hc-studio__btn is-ghost"
              onClick={() =>
                void act('rebuild', () => wikiApi.rebuild(projectId), '正在重建索引').then(() =>
                  notify('索引与总览已重建', 'success'),
                )
              }
            >
              重建索引
            </button>
          </div>
        </section>
      </div>

      {!reviews.length && !groups.length && !loading ? (
        <EmptyState title="目前没有需要人工介入的地方" hint="继续编译资料，或到图谱里查看知识缺口。" />
      ) : null}
    </div>
  )
}

export default ReviewPanel
