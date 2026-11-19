/** Wiki / 深度研究后端的类型化客户端。
 *  与 backend/app/wiki/api.py 一一对应，路径前缀统一为 /api/wiki。 */

export interface WikiProject {
  id: string
  name: string
  template?: string
  exists: boolean
  path?: string
  counts?: { sources: number; pages: number; reviews: number }
}

export interface QueueTask {
  id: string
  projectId: string
  sourcePath: string
  sourceName: string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  stage: string
  detail: string
  attempts: number
  error: string
  pagesWritten: string[]
  createdAt: string
  updatedAt: string
}

export interface WikiOverview {
  project: { id: string; name: string; path: string; exists: boolean }
  counts: {
    sources: number
    pages: number
    reviews: number
    lintErrors: number
    lintWarnings: number
    queue: number
  }
  health: number
  byType: { type: string; label: string; count: number }[]
  purpose: string
  queue: QueueTask[]
  settings: Record<string, unknown>
  llm: { available: boolean; provider: string; model?: string | null }
}

export interface PageSummary {
  path: string
  name: string
  dir: string
  type: string
  title: string
  tags: string[]
  related: string[]
  sources: string[]
  created: string
  updated: string
  size: number
  readingMinutes: number
  excerpt: string
}

export interface PageDetail {
  path: string
  meta: Record<string, unknown>
  content: string
  raw: string
  related: { id: string; title: string; type: string; path: string; score: number; reasons: string[] }[]
  backlinks: { id: string; title: string }[]
}

export interface SourceItem {
  name: string
  path: string
  size: number
  ext: string
  modifiedAt: string
  ingested: boolean
  hash: string
  wikiPage: string
  wikiPages: number
  ingestedAt: string
}

export interface GraphNode {
  id: string
  label: string
  type: string
  path: string
  community: number
  color: string
  linkCount: number
  sources: string[]
  updated: string
}

export interface GraphEdge {
  source: string
  target: string
  weight: number
  score: number
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  communities: { id: number; size: number; cohesion: number; color: string; label: string }[]
  stats: { pages: number; links: number; density: number }
}

export interface InsightData {
  surprising: {
    source: string
    sourceTitle: string
    target: string
    targetTitle: string
    score: number
    reasons: string[]
    key: string
  }[]
  gaps: {
    type: 'isolated-node' | 'sparse-community' | 'bridge-node'
    title: string
    description: string
    nodeIds: string[]
    suggestion: string
    seed: string
  }[]
}

export interface SearchHit {
  kind: string
  id: string
  title: string
  path: string
  type: string
  score: number
  snippet: string
  reasons: string[]
  sources: string[]
}

export interface SearchResult {
  items: SearchHit[]
  citations: {
    index: number
    id: string
    title: string
    path: string
    type: string
    sources: string[]
    score: number
    reason: string[]
  }[]
  context: string
  budget: { tokens: number; chars: number; pages: number; history: number; index: number; system: number }
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: SearchResult['citations']
  model?: string
  mode?: string
  createdAt: string
}

export interface ChatSession {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messageCount: number
}

export interface ChatAnswer {
  sessionId: string
  message: ChatMessage
  citations: SearchResult['citations']
  lowConfidence: boolean
}

export interface ResearchStep {
  key: string
  label: string
  status: 'pending' | 'running' | 'done'
}

export interface ResearchSource {
  index: number
  title: string
  url: string
}

export interface ResearchTask {
  id: string
  topic: string
  status: 'running' | 'completed' | 'error'
  stage: string
  progress: number
  steps: ResearchStep[]
  queries: string[]
  sources: ResearchSource[]
  pagePath: string
  content: string
  gaps: string[]
  archivedSources?: string[]
  autoIngest: boolean
  error?: string
  createdAt: string
  updatedAt: string
}

export type ReviewType = 'contradiction' | 'duplicate' | 'missing-page' | 'suggestion'

export interface ReviewItem {
  id: string
  type: ReviewType | string
  title: string
  description: string
  affectedPages?: string[]
  searchQueries?: string[]
  options?: { label: string; action: string }[]
  resolved?: boolean
  createdAt?: string
}

export interface LintIssue {
  level: 'error' | 'warning' | 'info' | string
  code: string
  file: string
  message: string
}

export interface LintResult {
  issues: LintIssue[]
  stats: { pages: number; errors: number; warnings: number; health: number; links: number }
  labels: Record<string, string>
}

const readError = (data: unknown, status: number) => {
  if (data && typeof data === 'object') {
    const record = data as { error?: unknown; detail?: unknown }
    if (typeof record.error === 'string' && record.error) return record.error
    if (typeof record.detail === 'string' && record.detail) return record.detail
  }
  return `请求失败（${status}）`
}

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const isFormData = init?.body instanceof FormData
  const headers = new Headers(init?.headers)
  if (!isFormData) headers.set('content-type', 'application/json')
  const response = await fetch(path, { ...init, headers })
  const data = (await response.json().catch(() => ({}))) as T & { error?: string; detail?: unknown }
  if (!response.ok) throw new Error(readError(data, response.status))
  return data
}

const withProject = (path: string, projectId: string) =>
  `${path}${path.includes('?') ? '&' : '?'}project=${encodeURIComponent(projectId)}`

export const wikiApi = {
  templates: () => request<{ items: { id: string; name: string; description: string; icon: string }[] }>('/api/wiki/templates'),
  projects: () => request<{ items: WikiProject[] }>('/api/wiki/projects'),
  init: (projectId: string, template: string) =>
    request<{ item: WikiProject }>(`/api/wiki/projects/${encodeURIComponent(projectId)}/init`, {
      method: 'POST',
      body: JSON.stringify({ template }),
    }),
  overview: (projectId: string) => request<WikiOverview>(withProject('/api/wiki/overview', projectId)),
  purpose: {
    get: (projectId: string) => request<{ content: string }>(withProject('/api/wiki/purpose', projectId)),
    set: (projectId: string, content: string) =>
      request<{ ok: boolean }>(withProject('/api/wiki/purpose', projectId), {
        method: 'PUT',
        body: JSON.stringify({ content }),
      }),
  },
  schema: {
    get: (projectId: string) => request<{ content: string }>(withProject('/api/wiki/schema', projectId)),
    set: (projectId: string, content: string) =>
      request<{ ok: boolean }>(withProject('/api/wiki/schema', projectId), {
        method: 'PUT',
        body: JSON.stringify({ content }),
      }),
  },
  settings: {
    get: (projectId: string) => request<{ item: Record<string, unknown> }>(withProject('/api/wiki/settings', projectId)),
    patch: (projectId: string, patch: Record<string, unknown>) =>
      request<{ item: Record<string, unknown> }>(withProject('/api/wiki/settings', projectId), {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),
  },
  sources: {
    list: (projectId: string) =>
      request<{ project: { id: string; name: string; exists: boolean }; items: SourceItem[] }>(
        withProject('/api/wiki/sources', projectId),
      ),
    upload: (projectId: string, files: File[]) => {
      const form = new FormData()
      form.append('project', projectId)
      files.forEach((file) => form.append('files', file, file.name))
      return request<{ items: string[]; tasks: QueueTask[] }>('/api/wiki/sources/upload', {
        method: 'POST',
        body: form,
      })
    },
    importDocuments: (projectId: string) =>
      request<{ items: string[]; missing: string[]; tasks: QueueTask[] }>(
        withProject('/api/wiki/sources/import', projectId),
        { method: 'POST' },
      ),
    remove: (projectId: string, path: string) =>
      request<{ ok: boolean; removedPages: string[]; touchedPages: string[] }>(
        withProject(`/api/wiki/sources?path=${encodeURIComponent(path)}`, projectId),
        { method: 'DELETE' },
      ),
    content: (projectId: string, path: string) =>
      request<{ name: string; content: string; chars: number }>(
        withProject(`/api/wiki/source/content?path=${encodeURIComponent(path)}`, projectId),
      ),
  },
  ingest: (projectId: string, paths: string[] = [], force = false) =>
    request<{ items: QueueTask[] }>(withProject('/api/wiki/ingest', projectId), {
      method: 'POST',
      body: JSON.stringify({ paths, force }),
    }),
  queue: (projectId: string) => request<{ items: QueueTask[] }>(withProject('/api/wiki/queue', projectId)),
  cancel: (projectId: string, taskId: string) =>
    request<{ ok: boolean }>(withProject(`/api/wiki/queue/${encodeURIComponent(taskId)}/cancel`, projectId), {
      method: 'POST',
    }),
  retry: (projectId: string, taskId: string) =>
    request<{ ok: boolean }>(withProject(`/api/wiki/queue/${encodeURIComponent(taskId)}/retry`, projectId), {
      method: 'POST',
    }),
  rebuild: (projectId: string) =>
    request<{ ok: boolean }>(withProject('/api/wiki/rebuild', projectId), { method: 'POST' }),
  reset: (projectId: string) =>
    request<{ ok: boolean }>(withProject('/api/wiki/reset', projectId), { method: 'POST' }),
  exportUrl: (projectId: string) => withProject('/api/wiki/export', projectId),
  pages: {
    list: (projectId: string) =>
      request<{ items: PageSummary[]; types: { type: string; label: string; count: number }[] }>(
        withProject('/api/wiki/pages', projectId),
      ),
    get: (projectId: string, file: string) =>
      request<PageDetail>(withProject(`/api/wiki/page?file=${encodeURIComponent(file)}`, projectId)),
    save: (projectId: string, path: string, content: string) =>
      request<{ ok: boolean; path: string }>(withProject('/api/wiki/page', projectId), {
        method: 'POST',
        body: JSON.stringify({ path, content }),
      }),
    create: (projectId: string, type: string, title: string, body: string) =>
      request<{ ok: boolean; path: string }>(withProject('/api/wiki/page', projectId), {
        method: 'POST',
        body: JSON.stringify({ type, title, body }),
      }),
    remove: (projectId: string, file: string) =>
      request<{ ok: boolean }>(withProject(`/api/wiki/page?file=${encodeURIComponent(file)}`, projectId), {
        method: 'DELETE',
      }),
  },
  graph: (projectId: string, type?: string, q?: string) => {
    const params = new URLSearchParams()
    if (type) params.set('type', type)
    if (q) params.set('q', q)
    const query = params.toString()
    return request<GraphData>(withProject(`/api/wiki/graph${query ? `?${query}` : ''}`, projectId))
  },
  insights: (projectId: string) => request<InsightData>(withProject('/api/wiki/insights', projectId)),
  search: (projectId: string, query: string, options?: { limit?: number; includeSources?: boolean; expand?: boolean }) =>
    request<SearchResult>(withProject('/api/wiki/search', projectId), {
      method: 'POST',
      body: JSON.stringify({
        query,
        limit: options?.limit ?? 8,
        include_sources: options?.includeSources ?? true,
        expand: options?.expand ?? true,
      }),
    }),
  sessions: {
    list: (projectId: string) => request<{ items: ChatSession[] }>(withProject('/api/wiki/sessions', projectId)),
    create: (projectId: string, title = '新对话') =>
      request<{ item: ChatSession }>(withProject('/api/wiki/sessions', projectId), {
        method: 'POST',
        body: JSON.stringify({ title }),
      }),
    get: (projectId: string, id: string) =>
      request<{ item: { id: string; messages: ChatMessage[] } }>(
        withProject(`/api/wiki/sessions/${encodeURIComponent(id)}`, projectId),
      ),
    rename: (projectId: string, id: string, title: string) =>
      request<{ item: ChatSession }>(withProject(`/api/wiki/sessions/${encodeURIComponent(id)}`, projectId), {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }),
    remove: (projectId: string, id: string) =>
      request<{ ok: boolean }>(withProject(`/api/wiki/sessions/${encodeURIComponent(id)}`, projectId), {
        method: 'DELETE',
      }),
  },
  chat: (projectId: string, question: string, sessionId?: string | null, mode = 'balanced') =>
    request<ChatAnswer>(withProject('/api/wiki/chat', projectId), {
      method: 'POST',
      body: JSON.stringify({ question, sessionId, mode }),
    }),
  saveChat: (projectId: string, question: string, answer: string, citations: SearchResult['citations']) =>
    request<{ ok: boolean; path: string }>(withProject('/api/wiki/chat/save', projectId), {
      method: 'POST',
      body: JSON.stringify({ question, answer, citations }),
    }),
  research: {
    list: (projectId: string) => request<{ items: ResearchTask[] }>(withProject('/api/wiki/research', projectId)),
    start: (projectId: string, topic: string, options?: { seedPages?: string[]; autoIngest?: boolean }) =>
      request<{ item: ResearchTask }>(withProject('/api/wiki/research', projectId), {
        method: 'POST',
        body: JSON.stringify({
          topic,
          seedPages: options?.seedPages ?? [],
          autoIngest: options?.autoIngest ?? true,
        }),
      }),
    get: (projectId: string, id: string) =>
      request<{ item: ResearchTask }>(withProject(`/api/wiki/research/${encodeURIComponent(id)}`, projectId)),
  },
  lint: (projectId: string) => request<LintResult>(withProject('/api/wiki/lint', projectId)),
  reviews: {
    list: (projectId: string) => request<{ items: ReviewItem[]; total: number }>(withProject('/api/wiki/reviews', projectId)),
    resolve: (projectId: string, id: string, action = 'Skip') =>
      request<{ item: ReviewItem }>(withProject(`/api/wiki/reviews/${encodeURIComponent(id)}`, projectId), {
        method: 'POST',
        body: JSON.stringify({ action }),
      }),
    resolveBatch: (projectId: string, ids: string[], action = 'Skip') =>
      request<{ resolved: number; count: number }>(withProject('/api/wiki/reviews/resolve', projectId), {
        method: 'POST',
        body: JSON.stringify({ ids, action }),
      }),
    createPage: (projectId: string, id: string) =>
      request<{ ok: boolean; path: string }>(
        withProject(`/api/wiki/reviews/${encodeURIComponent(id)}/create-page`, projectId),
        { method: 'POST' },
      ),
    research: (projectId: string, id: string) =>
      request<{ item: ResearchTask }>(
        withProject(`/api/wiki/reviews/${encodeURIComponent(id)}/research`, projectId),
        { method: 'POST' },
      ),
  },
}
