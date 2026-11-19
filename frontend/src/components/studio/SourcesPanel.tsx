import { useRef, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type SourceItem } from './wikiApi'
import { EmptyState, PanelHead, Tag, formatSize, formatTime } from './ui'
import Markdown from './Markdown'

interface Props {
  projectId: string
  sources: SourceItem[]
  loading: boolean
  onRefresh: () => void
  onOpenPage: (path: string) => void
}

const EXT_TONE: Record<string, string> = {
  pdf: 'rose',
  docx: 'indigo',
  doc: 'indigo',
  pptx: 'amber',
  xlsx: 'green',
  csv: 'green',
  md: 'violet',
  txt: 'slate',
}

const SourcesPanel = ({ projectId, sources, loading, onRefresh, onOpenPage }: Props) => {
  const { notify, track } = useFeedback()
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [busy, setBusy] = useState('')
  const [preview, setPreview] = useState<{ name: string; content: string } | null>(null)
  const [filter, setFilter] = useState('')

  const visible = sources.filter((item) => !filter || item.name.toLowerCase().includes(filter.toLowerCase()))
  const ingested = sources.filter((item) => item.ingested).length

  const upload = async (files: FileList | null) => {
    if (!files || !files.length) return
    setBusy('upload')
    const result = await track(() => wikiApi.sources.upload(projectId, Array.from(files)), {
      loading: `正在上传 ${files.length} 个文件`,
      success: '已加入编译队列',
      error: '上传失败',
    })
    setBusy('')
    if (inputRef.current) inputRef.current.value = ''
    if (result) onRefresh()
  }

  const remove = async (item: SourceItem) => {
    if (!window.confirm(`删除原始资料《${item.name}》？关联的摘要页与引用会被级联清理。`)) return
    setBusy(item.path)
    const result = await track(() => wikiApi.sources.remove(projectId, item.path), {
      loading: '正在删除并清理关联页面',
      success: '已删除并级联清理',
      error: '删除失败',
    })
    setBusy('')
    if (result) onRefresh()
  }

  const compile = async (item: SourceItem, force = false) => {
    setBusy(`ingest-${item.path}`)
    const result = await track(() => wikiApi.ingest(projectId, [item.path], force), {
      loading: `正在编译《${item.name}》`,
      success: '已加入编译队列',
      error: '编译失败',
    })
    setBusy('')
    if (result) onRefresh()
  }

  const openPreview = async (item: SourceItem) => {
    setBusy(`preview-${item.path}`)
    const result = await track(() => wikiApi.sources.content(projectId, item.path), { error: '无法解析该资料' })
    setBusy('')
    if (result) setPreview(result)
  }

  return (
    <div className="hc-studio__panel">
      <PanelHead
        title="原始资料"
        hint={`${sources.length} 份 · ${ingested} 已编译 · 原件不可变，所有加工写入 wiki/`}
        actions={
          <>
            <button
              type="button"
              className="hc-studio__btn is-ghost"
              disabled={busy === 'import'}
              onClick={async () => {
                setBusy('import')
                const result = await track(() => wikiApi.sources.importDocuments(projectId), {
                  loading: '正在导入知识库文档',
                  success: '已导入并加入队列',
                  error: '导入失败',
                })
                setBusy('')
                if (result) {
                  if (result.missing.length) notify(`${result.missing.length} 份文档缺少本地原件，已跳过`, 'info')
                  onRefresh()
                }
              }}
            >
              导入知识库文档
            </button>
            <button type="button" className="hc-studio__btn" onClick={() => void compileAll()} disabled={!sources.length}>
              全部编译
            </button>
            <button
              type="button"
              className="hc-studio__btn is-primary"
              onClick={() => inputRef.current?.click()}
              disabled={busy === 'upload'}
            >
              {busy === 'upload' ? '上传中…' : '上传资料'}
            </button>
          </>
        }
      />

      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        onChange={(event) => void upload(event.target.files)}
        accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.markdown,.html,.htm,.json,.mhtml"
      />

      <div className="hc-studio__toolbar">
        <input
          className="hc-studio__input"
          placeholder="按文件名筛选"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <span className="hc-studio__muted">支持 PDF / Office / Markdown / 网页存档；文件夹结构会保留为编译上下文</span>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          title={loading ? '正在读取资料…' : '还没有原始资料'}
          hint="上传资料后会自动进入两步式编译：先分析结构，再生成带 frontmatter 的 wiki 页面。"
          action={
            <button type="button" className="hc-studio__btn is-primary" onClick={() => inputRef.current?.click()}>
              选择文件
            </button>
          }
        />
      ) : (
        <ul className="hc-studio__list">
          {visible.map((item) => (
            <li key={item.path} className="hc-studio__row">
              <span className={`hc-studio__file is-${EXT_TONE[item.ext] || 'slate'}`}>{item.ext || 'file'}</span>
              <div className="hc-studio__row-main">
                <div className="hc-studio__row-title" title={item.name}>
                  {item.name}
                </div>
                <div className="hc-studio__row-meta">
                  {formatSize(item.size)} · {formatTime(item.modifiedAt)}
                  {item.ingestedAt ? ` · 编译于 ${formatTime(item.ingestedAt)}` : ''}
                  {item.wikiPages ? ` · ${item.wikiPages} 页` : ''}
                </div>
              </div>
              <Tag tone={item.ingested ? 'green' : 'slate'}>{item.ingested ? '已编译' : '未编译'}</Tag>
              <div className="hc-studio__row-actions">
                <button type="button" className="hc-studio__link" onClick={() => void openPreview(item)}>
                  预览
                </button>
                {item.wikiPage ? (
                  <button type="button" className="hc-studio__link" onClick={() => onOpenPage(item.wikiPage)}>
                    摘要页
                  </button>
                ) : null}
                <button
                  type="button"
                  className="hc-studio__link"
                  disabled={busy === `ingest-${item.path}`}
                  onClick={() => void compile(item, item.ingested)}
                >
                  {item.ingested ? '重新编译' : '编译'}
                </button>
                <button type="button" className="hc-studio__link is-danger" onClick={() => void remove(item)}>
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {preview ? (
        <div className="hc-studio__drawer" role="dialog" aria-label="资料来源预览">
          <header className="hc-studio__drawer-head">
            <div>
              <strong>{preview.name}</strong>
              <span className="hc-studio__muted">解析后文本 · {preview.content.length} 字</span>
            </div>
            <button type="button" className="hc-studio__btn is-ghost" onClick={() => setPreview(null)}>
              关闭
            </button>
          </header>
          <div className="hc-studio__drawer-body">
            <Markdown content={preview.content.slice(0, 20000)} compact />
          </div>
        </div>
      ) : null}
    </div>
  )

  async function compileAll() {
    setBusy('all')
    const result = await track(() => wikiApi.ingest(projectId), {
      loading: '正在排队编译全部资料',
      success: '已加入编译队列',
      error: '操作失败',
    })
    setBusy('')
    if (result) onRefresh()
  }
}

export default SourcesPanel
