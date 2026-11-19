import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { api, type DocumentItem, type Project } from '@/services/api'
import { useFeedback } from '@/components/Feedback'
import { setCurrentProject } from '@/utils/project'

type ProjectRow = Project & { documentCount?: number }

const ProjectSidebarList = ({ currentProjectId }: { currentProjectId?: string }) => {
    const navigate = useNavigate()
    const location = useLocation()
    const { notify } = useFeedback()
    const [projects, setProjects] = useState<ProjectRow[]>([])
    const [loading, setLoading] = useState(true)
    const [pendingDelete, setPendingDelete] = useState<string | null>(null)
    const [deletingId, setDeletingId] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            try {
                const [projectResponse, documentResponse] = await Promise.all([
                    api.projects.list(),
                    api.documents.list().catch(() => ({ items: [] as DocumentItem[] })),
                ])
                if (cancelled) return
                const counts = new Map<string, number>()
                documentResponse.items.forEach((item) => {
                    counts.set(item.projectId, (counts.get(item.projectId) || 0) + 1)
                })
                setProjects(
                    (projectResponse.items || []).map((project) => ({
                        ...project,
                        documentCount: counts.get(project.id) || 0,
                    })),
                )
            } catch {
                // 后端未启动时保留空列表，不打断页面其它功能
                if (!cancelled) setProjects([])
            } finally {
                if (!cancelled) setLoading(false)
            }
        }
        void load()
        return () => {
            cancelled = true
        }
    }, [])

    const select = (project: ProjectRow) => {
        setPendingDelete(null)
        setCurrentProject({ id: project.id, name: project.name })
        notify(`已切换到项目：${project.name}`)
        // 点击项目后直接进入该项目的资料上传页
        navigate('/frame2688', {
            state: { projectId: project.id, projectName: project.name },
            replace: location.pathname === '/frame2688',
        })
    }

    const removeProject = async (project: ProjectRow) => {
        if (pendingDelete !== project.id) {
            setPendingDelete(project.id)
            return
        }
        setDeletingId(project.id)
        try {
            await api.projects.remove(project.id)
            const remaining = projects.filter((item) => item.id !== project.id)
            setProjects(remaining)
            if (project.id === currentProjectId) {
                const fallback = remaining[0] ?? { id: 'default', name: '默认知识库' }
                setCurrentProject({ id: fallback.id, name: fallback.name })
                navigate(location.pathname, {
                    state: { projectId: fallback.id, projectName: fallback.name },
                })
            }
            notify(`已删除项目：${project.name}`, 'success')
        } catch {
            notify('删除项目失败，请稍后重试', 'error')
        } finally {
            setDeletingId(null)
            setPendingDelete(null)
        }
    }

    return (
        <div className="hc-project-panel">
            <div className="hc-project-list">
                {loading ? (
                    <div className="hc-project-list__empty">项目读取中…</div>
                ) : projects.length === 0 ? (
                    <div className="hc-project-list__empty">暂无项目，点击上方「新建项目」开始</div>
                ) : (
                    projects.slice(0, 8).map((project) => {
                        const active = project.id === currentProjectId
                        const confirming = pendingDelete === project.id
                        return (
                            <div
                                key={project.id}
                                className={`hc-project-list__item${active ? ' is-active' : ''}`}
                            >
                                <button
                                    type="button"
                                    className="hc-project-list__select"
                                    title={project.name}
                                    onClick={() => select(project)}
                                >
                                    <span className="hc-project-list__name">{project.name}</span>
                                    <span className="hc-project-list__meta">
                                        {project.documentCount
                                            ? `${project.documentCount} 份资料`
                                            : '暂无资料'}
                                    </span>
                                </button>
                                {project.id !== 'default' ? (
                                    <button
                                        type="button"
                                        className={`hc-project-list__delete${confirming ? ' is-confirming' : ''}`}
                                        disabled={deletingId === project.id}
                                        onClick={() => void removeProject(project)}
                                    >
                                        {deletingId === project.id
                                            ? '删除中…'
                                            : confirming
                                              ? '确定删除'
                                              : '删除'}
                                    </button>
                                ) : null}
                            </div>
                        )
                    })
                )}
            </div>
            <button
                type="button"
                className="hc-project-settings"
                onClick={() => navigate('/frame2688')}
            >
                项目设置
            </button>
        </div>
    )
}

export default ProjectSidebarList
