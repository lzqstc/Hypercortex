export interface Project {
  id: string
  name: string
  template: string
  team: string
  visibility: string
  createdAt: string
}

export interface UploadFile {
  id: string
  name: string
  size: number
  status: string
  progress: number
  error?: string | null
  pages?: number
  chunks?: number
  createdAt: string
}

export interface UploadJob {
  id: string
  projectId?: string
  type?: string
  files: UploadFile[]
  total: number
  status: string
  processed?: number
  error?: string | null
  createdAt: string
}

export interface ChatSource {
  id: string
  documentId?: string
  title: string
  filename?: string
  sourceUrl?: string | null
  page?: number | null
  section?: string
  chunkIndex?: number
  score: number
  vectorScore?: number
  rerankScore?: number
  rank?: number
  snippet?: string
  content?: string
}

export interface ChatAnswer {
  id: string
  projectId?: string
  question: string
  answer: string
  sources: ChatSource[]
  model?: string
  latencyMs?: number
  lowConfidence?: boolean
  createdAt: string
}

export interface DocumentItem {
  id: string
  projectId: string
  filename: string
  kind: string
  mime: string
  size: number
  status: string
  progress: number
  pages: number
  chunks: number
  error?: string | null
  createdAt: string
  downloadUrl?: string | null
}

export interface ResearchTask {
  id: string
  topic: string
  status: string
  steps: string[]
  createdAt: string
}

export interface ResearchDetail extends ResearchTask {
  projectId?: string
  updatedAt?: string
  result?: WikiCard | null
  error?: string | null
}

export interface WikiCard {
  id: string
  researchId?: string
  projectId: string
  title: string
  content: string
  sources: ChatSource[]
  confidence?: number
  archived?: boolean
  createdAt: string
}

export interface Settings {
  autoSync: boolean
  deepSearch: boolean
  citations: boolean
}

export interface BootstrapData {
  projects: Project[]
  uploads: UploadJob[]
  conversations: ChatAnswer[]
  researches: ResearchTask[]
  notifications: Array<{ id: string; title: string; detail: string; read: boolean }>
  settings: Settings
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
  if (!response.ok) {
    throw new Error(readError(data, response.status))
  }
  return data
}

export const api = {
  health: () => request<{ ok: boolean; service: string }>('/api/health'),
  bootstrap: () => request<BootstrapData>('/api/bootstrap'),
  projects: {
    list: () => request<{ items: Project[] }>('/api/projects'),
    create: (payload: { name: string; template: string; team: string; visibility: string }) =>
      request<{ item: Project }>('/api/projects', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    remove: (projectId: string) =>
      request<{ ok: boolean }>(`/api/projects/${encodeURIComponent(projectId)}`, {
        method: 'DELETE',
      }),
  },
  uploads: {
    create: (files: File[], projectId = 'default') => {
      const form = new FormData()
      form.append('project_id', projectId)
      files.forEach((file) => form.append('files', file, file.name))
      return request<{ item: UploadJob }>('/api/uploads', {
        method: 'POST',
        body: form,
      })
    },
    get: (jobId: string) => request<{ item: UploadJob }>(`/api/uploads/${jobId}`),
    url: (url: string, projectId = 'default') =>
      request<{ item: UploadJob }>('/api/uploads/url', {
        method: 'POST',
        body: JSON.stringify({ url, projectId }),
      }),
    cloud: (provider: string, projectId = 'default') =>
      request<{ item: UploadJob }>('/api/uploads/cloud', {
        method: 'POST',
        body: JSON.stringify({ provider, projectId }),
      }),
  },
  documents: {
    list: (projectId?: string) =>
      request<{ items: DocumentItem[] }>(
        `/api/documents${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
      ),
    remove: (documentId: string) =>
      request<{ ok: boolean }>(`/api/documents/${documentId}`, { method: 'DELETE' }),
  },
  chat: {
    ask: (
      question: string,
      options?: {
        projectId?: string
        topK?: number
        citations?: boolean
        history?: { role: 'user' | 'assistant'; content: string }[]
      },
    ) =>
      request<{ item: ChatAnswer }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          question,
          projectId: options?.projectId || 'default',
          topK: options?.topK || 6,
          citations: options?.citations ?? true,
          history: options?.history ?? [],
        }),
      }),
  },
  search: (query: string, projectId = 'default', topK = 6) =>
    request<{ items: ChatSource[]; lowConfidence: boolean }>('/api/search', {
      method: 'POST',
      body: JSON.stringify({ query, projectId, topK }),
    }),
  research: {
    list: (projectId?: string) =>
      request<{ items: ResearchTask[] }>(
        `/api/research${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
      ),
    start: (topic: string, projectId = 'default') =>
      request<{ item: ResearchTask }>('/api/research', {
        method: 'POST',
        body: JSON.stringify({ topic, projectId }),
      }),
    get: (id: string) => request<{ item: ResearchDetail }>(`/api/research/${encodeURIComponent(id)}`),
    run: (id: string, topic?: string) =>
      request<{ item: ResearchDetail }>(`/api/research/${encodeURIComponent(id)}/run`, {
        method: 'POST',
        body: JSON.stringify(topic ? { topic } : {}),
      }),
    archive: (id: string) =>
      request<{ item: WikiCard }>(`/api/research/${encodeURIComponent(id)}/archive`, {
        method: 'POST',
      }),
  },
  cards: {
    list: (projectId?: string) =>
      request<{ items: WikiCard[] }>(
        `/api/cards${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
      ),
  },
  settings: {
    update: (payload: Partial<Settings>) =>
      request<{ item: Settings }>('/api/settings', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
  },
  notifications: {
    list: () => request<{ items: BootstrapData['notifications'] }>('/api/notifications'),
  },
}
