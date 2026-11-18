export interface CurrentProject {
  id: string
  name: string
}

const STORAGE_KEY = 'hypercortex.currentProject'

export const defaultProject: CurrentProject = {
  id: 'default',
  name: '默认知识库',
}

export const getCurrentProject = (): CurrentProject => {
  if (typeof window === 'undefined') return defaultProject
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultProject
    const parsed = JSON.parse(raw) as Partial<CurrentProject>
    if (!parsed.id || !parsed.name) return defaultProject
    return { id: parsed.id, name: parsed.name }
  } catch {
    return defaultProject
  }
}

export const setCurrentProject = (project: CurrentProject) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(project))
}
