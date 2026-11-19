import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ResearchDetail, type ResearchTask } from '@/services/api'
import { useFeedback } from '@/components/Feedback'
import { getCurrentProject } from '@/utils/project'

const STEP_LABELS = [
    '拆解研究主题',
    '检索并聚类证据',
    '交叉验证矛盾点',
    '生成结构化结论',
    '输出 wiki 卡片',
]

const DEFAULT_TOPIC = '当前知识库中，最近资料反复出现的风险点是什么？请给出结论、依据与建议动作。'

const ResearchWorkspace = ({ projectId }: { projectId?: string }) => {
    const { notify, track } = useFeedback()
    const activeProject = projectId || getCurrentProject().id
    const [topic, setTopic] = useState('')
    const [task, setTask] = useState<ResearchDetail | null>(null)
    const [history, setHistory] = useState<ResearchTask[]>([])
    const [loading, setLoading] = useState(true)
    const [running, setRunning] = useState(false)
    const [progress, setProgress] = useState(0)
    const [editing, setEditing] = useState(false)
    const [draft, setDraft] = useState('')
    const timer = useRef<number | null>(null)

    const stopTimer = () => {
        if (timer.current !== null) {
            window.clearInterval(timer.current)
            timer.current = null
        }
    }

    useEffect(() => () => stopTimer(), [])

    const load = useCallback(async () => {
        setLoading(true)
        try {
            const response = await api.research.list(activeProject)
            const items = response.items || []
            setHistory(items.slice(0, 6))
            if (items.length) {
                const detail = await api.research.get(items[0].id)
                setTask(detail.item)
            } else {
                setTask(null)
            }
        } catch {
            // 后端尚未启动时保留空工作台，用户仍可输入主题
            setHistory([])
            setTask(null)
        } finally {
            setLoading(false)
        }
    }, [activeProject])

    useEffect(() => {
        void load()
    }, [load])

    const startResearch = async () => {
        const value = topic.trim()
        if (!value) {
            notify('请先输入研究主题', 'error')
            return
        }
        if (running) return
        setRunning(true)
        setProgress(0)
        stopTimer()
        timer.current = window.setInterval(() => {
            setProgress((current) => Math.min(STEP_LABELS.length - 1, current + 1))
        }, 520)
        const result = await track(
            async () => {
                const created = await api.research.start(value, activeProject)
                if (!created?.item) throw new Error('研究任务创建失败')
                return api.research.run(created.item.id)
            },
            { loading: '正在检索资料并生成研究结论…', error: '研究失败，请稍后重试' },
        )
        stopTimer()
        setRunning(false)
        if (result?.item) {
            setTask(result.item)
            setProgress(STEP_LABELS.length)
            setHistory((current) => [result.item, ...current.filter((item) => item.id !== result.item.id)].slice(0, 6))
            notify('研究结论已生成', 'success')
        } else {
            setProgress(0)
        }
    }

    const selectHistory = async (id: string) => {
        const detail = await track(() => api.research.get(id), { error: '读取研究记录失败' })
        if (detail?.item) {
            setTask(detail.item)
            setTopic(detail.item.topic)
            setProgress(STEP_LABELS.length)
        }
    }

    const archive = async () => {
        if (!task) return
        const result = await track(() => api.research.archive(task.id), {
            loading: '正在归档到知识库…',
            success: '已归档为 wiki 卡片',
            error: '归档失败，请稍后重试',
        })
        if (result?.item) {
            setTask((current) => (current ? { ...current, result: result.item } : current))
        }
    }

    const copyCard = async () => {
        if (!task?.result) return
        const text = `${task.result.title}\n\n${task.result.content}`
        try {
            await navigator.clipboard.writeText(text)
            notify('研究卡片已复制', 'success')
        } catch {
            notify('浏览器未授权剪贴板，请手动选择文本', 'error')
        }
    }

    const steps = task?.steps?.length ? task.steps : STEP_LABELS
    const doneSteps = running ? progress : task?.status === 'completed' ? steps.length : task ? progress : 0
    const result = task?.result
    const isExpanded = Boolean(task || running)

    return (
        <section className={`hc-research${isExpanded ? ' is-expanded' : ''}`} aria-label="深度思考与研究">
            <div className="hc-research__head">
                <div className="hc-research__title">
                    <span className="hc-research__dot" aria-hidden="true" />
                    研究工作台
                    {loading ? <span className="hc-research__status">读取中…</span> : null}
                </div>
                <span
                    className={`hc-research__status${running ? ' is-running' : ''}${task?.status === 'completed' ? ' is-done' : ''}`}
                >
                    {running ? '研究进行中' : task?.status === 'completed' ? '已完成' : task ? '待继续' : '就绪'}
                </span>
            </div>
            <div className="hc-research__body">
                <label className="hc-research__meta" htmlFor="hc-research-topic">研究主题</label>
                <textarea
                    id="hc-research-topic"
                    className="hc-research__topic"
                    value={topic}
                    maxLength={2000}
                    placeholder={DEFAULT_TOPIC}
                    onChange={(event) => setTopic(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                            event.preventDefault()
                            void startResearch()
                        }
                    }}
                />
                <div className="hc-research__actions">
                    <span className="hc-research__meta">Ctrl / ⌘ + Enter 快速开始 · 结论可归档为 wiki 卡片</span>
                    <button
                        type="button"
                        className="hc-research__button"
                        disabled={running}
                        onClick={() => void startResearch()}
                    >
                        {running ? '研究中…' : '开始研究'}
                    </button>
                </div>

                {task || running ? (
                    <div className="hc-research__steps" aria-label="研究进度">
                        {steps.map((step, index) => (
                            <div
                                key={`${step}-${index}`}
                                className={`hc-research__step${index < doneSteps ? ' is-done' : ''}`}
                            >
                                <span className="hc-research__step-mark">{index < doneSteps ? '✓' : index + 1}</span>
                                {step}
                            </div>
                        ))}
                    </div>
                ) : null}

                {result ? (
                    <div className="hc-research__card">
                        <div className="hc-research__card-head">
                            <span className="hc-research__tag">WIKI · {result.archived ? '已归档' : '结论卡片'}</span>
                            <span className="hc-research__card-title">{result.title}</span>
                        </div>
                        {editing ? (
                            <textarea
                                className="hc-research__topic"
                                value={draft}
                                onChange={(event) => setDraft(event.target.value)}
                                aria-label="编辑研究结论"
                            />
                        ) : (
                            <p className="hc-research__card-text">{result.content}</p>
                        )}
                        <div className="hc-research__card-meta">
                            <span>{result.sources?.length || 0} 条引用来源</span>
                            {typeof result.confidence === 'number' ? (
                                <span>置信度 {Math.round(result.confidence * 100)}%</span>
                            ) : null}
                            <span>{result.archived ? '已进入知识库' : '归档后可进入知识库检索'}</span>
                        </div>
                        <div className="hc-research__card-actions">
                            <button
                                type="button"
                                className="hc-research__action"
                                onClick={() => {
                                    if (editing) {
                                        setEditing(false)
                                        notify('结论修改已保存在当前会话', 'success')
                                    } else {
                                        setDraft(result.content)
                                        setEditing(true)
                                    }
                                }}
                            >
                                {editing ? '完成编辑' : '编辑'}
                            </button>
                            <button type="button" className="hc-research__action" onClick={() => void copyCard()}>
                                复制
                            </button>
                            <button
                                type="button"
                                className="hc-research__action is-primary"
                                disabled={Boolean(result.archived)}
                                onClick={() => void archive()}
                            >
                                {result.archived ? '已归档' : '归档到知识库'}
                            </button>
                        </div>
                    </div>
                ) : null}

                {history.length ? (
                    <div className="hc-research__history">
                        {history.map((item) => (
                            <button
                                key={item.id}
                                type="button"
                                className="hc-research__history-item"
                                title={item.topic}
                                onClick={() => void selectHistory(item.id)}
                            >
                                {item.topic}
                            </button>
                        ))}
                    </div>
                ) : null}
            </div>
        </section>
    )
}

export default ResearchWorkspace
