/** 研究工作室的通用小组件与格式化工具。 */
import type { ReactNode } from 'react'

export const TYPE_LABELS: Record<string, string> = {
  entity: '实体',
  concept: '概念',
  source: '来源',
  query: '问题',
  comparison: '对比',
  synthesis: '综合',
  thesis: '论点',
  methodology: '方法',
  finding: '发现',
  decision: '决策',
  process: '流程',
  metric: '指标',
  author: '作者',
  other: '其他',
}

export const typeLabel = (type: string) => TYPE_LABELS[type] || type || '未分类'

export const formatSize = (size: number) => {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${Math.round(size / 1024)} KB`
  return `${size} B`
}

export const formatTime = (iso?: string) => {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const now = Date.now()
  const diff = now - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

export const shortPath = (path: string) => {
  const normalized = (path || '').replace(/\\/g, '/')
  const index = normalized.indexOf('wiki/')
  return index >= 0 ? normalized.slice(index) : normalized
}

export const PanelHead = ({
  title,
  hint,
  actions,
}: {
  title: string
  hint?: string
  actions?: ReactNode
}) => (
  <div className="hc-studio__head">
    <div className="hc-studio__head-main">
      <h2>{title}</h2>
      {hint ? <p>{hint}</p> : null}
    </div>
    {actions ? <div className="hc-studio__head-actions">{actions}</div> : null}
  </div>
)

export const EmptyState = ({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) => (
  <div className="hc-studio__empty">
    <div className="hc-studio__empty-mark" aria-hidden="true">
      ◍
    </div>
    <strong>{title}</strong>
    {hint ? <p>{hint}</p> : null}
    {action}
  </div>
)

export const Tag = ({ children, tone = 'slate' }: { children: ReactNode; tone?: string }) => (
  <span className={`hc-studio__tag is-${tone}`}>{children}</span>
)

export const Meter = ({ value, max = 1, tone = 'indigo' }: { value: number; max?: number; tone?: string }) => {
  const ratio = Math.max(0, Math.min(1, max > 0 ? value / max : 0))
  return (
    <span className={`hc-studio__meter is-${tone}`} aria-hidden="true">
      <span style={{ width: `${Math.round(ratio * 100)}%` }} />
    </span>
  )
}

export const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '编译中',
  done: '已完成',
  error: '失败',
  cancelled: '已取消',
}

export const Spinner = ({ label }: { label?: string }) => (
  <span className="hc-studio__spinner" role="status">
    <span className="hc-studio__spinner-dot" />
    {label ? <span>{label}</span> : null}
  </span>
)
