import { useEffect, useMemo, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type PageDetail, type PageSummary } from './wikiApi'
import { EmptyState, Tag, formatTime, shortPath, typeLabel } from './ui'
import Markdown from './Markdown'

interface Props {
  projectId: string
  pages: PageSummary[]
  types: { type: string; label: string; count: number }[]
  selected: string
  loading: boolean
  onSelect: (path: string) => void
  onRefresh: () => void
  onExternal: (url: string) => void
}

const PagesPanel = ({ projectId, pages, types, selected, loading, onSelect, onRefresh, onExternal }: Props) => {
  const { notify, track } = useFeedback()
  const [detail, setDetail] = useState<PageDetail | null>(null)
  const [filter, setFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newType, setNewType] = useState('concept')

  useEffect(() => {
    if (!selected) {
      setDetail(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const data = await wikiApi.pages.get(projectId, selected)
        if (!cancelled) setDetail(data)
      } catch {
        if (!cancelled) setDetail(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId, selected])

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return pages
      .filter((page) => (typeFilter ? page.type === typeFilter : true))
      .filter((page) => !needle || page.title.toLowerCase().includes(needle) || page.excerpt.toLowerCase().includes(needle))
      .sort((a, b) => (b.updated || '').localeCompare(a.updated || ''))
  }, [pages, filter, typeFilter])

  const grouped = useMemo(() => {
    const map = new Map<string, PageSummary[]>()
    visible.forEach((page) => {
      const list = map.get(page.type) || []
      list.push(page)
      map.set(page.type, list)
    })
    return [...map.entries()]
  }, [visible])

  const openByTitle = (title: string) => {
    const target = pages.find((page) => page.title === title || page.name === title)
    if (target) {
      onSelect(target.path)
      setEditing(null)
    } else {
      notify(`还没有「${title}」这个页面，可在审阅里创建`, 'info')
    }
  }

  const save = async () => {
    if (!editing) return
    const result = await track(() => wikiApi.pages.save(projectId, editing, draft), {
      loading: '正在保存页面',
      success: '页面已保存',
      error: '保存失败',
    })
    if (result) {
      setEditing(null)
      const data = await wikiApi.pages.get(projectId, editing)
      setDetail(data)
      onRefresh()
    }
  }

  const remove = async () => {
    if (!detail) return
    if (!window.confirm(`删除页面《${detail.path}》？该操作不可撤销。`)) return
    const result = await track(() => wikiApi.pages.remove(projectId, detail.path), {
      loading: '正在删除页面',
      success: '页面已删除',
      error: '删除失败',
    })
    if (result) {
      setDetail(null)
      onSelect('')
      onRefresh()
    }
  }

  const create = async () => {
    const title = newTitle.trim()
    if (!title) {
      notify('请填写页面标题', 'error')
      return
    }
    const result = await track(
      () => wikiApi.pages.create(projectId, newType, title, `# ${title}\n\n## 要点\n\n- \n`),
      { loading: '正在创建页面', success: '页面已创建', error: '创建失败' },
    )
    if (result) {
      setCreating(false)
      setNewTitle('')
      onRefresh()
      onSelect(result.path)
    }
  }

  return (
    <div className="hc-studio__panel hc-studio__panel--split">
      <aside className="hc-studio__side">
        <div className="hc-studio__side-head">
          <strong>知识页面</strong>
          <span className="hc-studio__muted">{pages.length} 页</span>
        </div>
        <input
          className="hc-studio__input"
          placeholder="搜索标题或内容"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <div className="hc-studio__chips">
          <button
            type="button"
            className={`hc-studio__chip${typeFilter === '' ? ' is-active' : ''}`}
            onClick={() => setTypeFilter('')}
          >
            全部 {pages.length}
          </button>
          {types.map((item) => (
            <button
              key={item.type}
              type="button"
              className={`hc-studio__chip${typeFilter === item.type ? ' is-active' : ''}`}
              onClick={() => setTypeFilter(item.type)}
            >
              {item.label} {item.count}
            </button>
          ))}
        </div>
        <button type="button" className="hc-studio__btn is-block" onClick={() => setCreating((value) => !value)}>
          + 新建页面
        </button>
        {creating ? (
          <div className="hc-studio__create">
            <input
              className="hc-studio__input"
              placeholder="页面标题"
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void create()
              }}
            />
            <select className="hc-studio__input" value={newType} onChange={(event) => setNewType(event.target.value)}>
              {types.map((item) => (
                <option key={item.type} value={item.type}>
                  {item.label}
                </option>
              ))}
            </select>
            <button type="button" className="hc-studio__btn is-primary" onClick={() => void create()}>
              创建
            </button>
          </div>
        ) : null}
        <div className="hc-studio__tree">
          {grouped.length === 0 ? (
            <p className="hc-studio__muted hc-studio__tree-empty">
              {loading ? '读取中…' : pages.length ? '没有匹配的页面' : '还没有编译出页面'}
            </p>
          ) : (
            grouped.map(([type, items]) => (
              <div key={type} className="hc-studio__tree-group">
                <div className="hc-studio__tree-head">
                  <span>{typeLabel(type)}</span>
                  <span>{items.length}</span>
                </div>
                {items.map((page) => (
                  <button
                    key={page.path}
                    type="button"
                    className={`hc-studio__tree-item${selected === page.path ? ' is-active' : ''}`}
                    onClick={() => {
                      onSelect(page.path)
                      setEditing(null)
                    }}
                    title={page.title}
                  >
                    <span className="hc-studio__tree-title">{page.title}</span>
                    <span className="hc-studio__tree-meta">{formatTime(page.updated)}</span>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      </aside>

      <section className="hc-studio__reader">
        {!detail ? (
          <EmptyState
            title={pages.length ? '选择左侧页面开始阅读' : '还没有知识页面'}
            hint={pages.length ? '支持 [[wikilink]] 跳转、关联推荐与来源溯源。' : '先在「来源」导入资料并编译，或手动新建页面。'}
          />
        ) : (
          <>
            <header className="hc-studio__reader-head">
              <div>
                <div className="hc-studio__reader-tags">
                  <Tag tone="indigo">{typeLabel(detail.meta.type as string)}</Tag>
                  {(Array.isArray(detail.meta.tags) ? (detail.meta.tags as string[]) : []).slice(0, 5).map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                  {detail.meta.updated ? <span className="hc-studio__muted">更新于 {String(detail.meta.updated)}</span> : null}
                </div>
                <h1>{String(detail.meta.title || detail.path)}</h1>
                <p className="hc-studio__reader-path">{shortPath(detail.path)}</p>
              </div>
              <div className="hc-studio__reader-actions">
                <button
                  type="button"
                  className="hc-studio__btn is-ghost"
                  onClick={() => {
                    if (editing) {
                      setEditing(null)
                    } else {
                      setEditing(detail.path)
                      setDraft(detail.raw)
                    }
                  }}
                >
                  {editing ? '取消编辑' : '编辑'}
                </button>
                <button type="button" className="hc-studio__btn is-ghost is-danger" onClick={() => void remove()}>
                  删除
                </button>
              </div>
            </header>

            <div className="hc-studio__reader-body">
              {editing ? (
                <>
                  <textarea
                    className="hc-studio__textarea is-code"
                    value={draft}
                    rows={24}
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <div className="hc-studio__card-actions">
                    <span className="hc-studio__muted">直接编辑原始 markdown（含 frontmatter）</span>
                    <button type="button" className="hc-studio__btn is-primary" onClick={() => void save()}>
                      保存页面
                    </button>
                  </div>
                </>
              ) : (
                <Markdown content={detail.content} onWikiLink={openByTitle} onExternal={onExternal} />
              )}
            </div>

            {detail.related.length || detail.backlinks.length || (detail.meta.sources as string[] | undefined)?.length ? (
              <footer className="hc-studio__reader-foot">
                {(detail.meta.sources as string[] | undefined)?.length ? (
                  <div className="hc-studio__foot-block">
                    <span className="hc-studio__muted">来源</span>
                    <div className="hc-studio__chips">
                      {(detail.meta.sources as string[]).map((source) => (
                        <Tag key={source} tone="green">
                          {source}
                        </Tag>
                      ))}
                    </div>
                  </div>
                ) : null}
                {detail.related.length ? (
                  <div className="hc-studio__foot-block">
                    <span className="hc-studio__muted">强关联</span>
                    <div className="hc-studio__chips">
                      {detail.related.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="hc-studio__chip"
                          onClick={() => onSelect(item.path)}
                          title={item.reasons.join(' · ')}
                        >
                          {item.title} · {item.score.toFixed(1)}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                {detail.backlinks.length ? (
                  <div className="hc-studio__foot-block">
                    <span className="hc-studio__muted">被引用</span>
                    <div className="hc-studio__chips">
                      {detail.backlinks.map((item) => (
                        <button key={item.id} type="button" className="hc-studio__chip" onClick={() => openByTitle(item.title)}>
                          {item.title}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </footer>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

export default PagesPanel
