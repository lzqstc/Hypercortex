import { useState } from 'react'
import { api, type ChatSource } from '@/services/api'
import { getCurrentProject } from '@/utils/project'

const QuickSearch = ({ onClose }: { onClose: () => void }) => {
    const [query, setQuery] = useState('')
    const [results, setResults] = useState<ChatSource[]>([])
    const [loading, setLoading] = useState(false)
    const [lowConfidence, setLowConfidence] = useState(false)
    const [error, setError] = useState('')

    const submit = async () => {
        const value = query.trim()
        if (!value) return
        setLoading(true)
        setError('')
        try {
            const response = await api.search(value, getCurrentProject().id, 6)
            setResults(response.items || [])
            setLowConfidence(Boolean(response.lowConfidence))
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : '检索失败')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="hc-quicksearch" role="dialog" aria-modal="true" aria-label="全局检索">
            <div className="hc-quicksearch__panel">
                <div className="hc-quicksearch__head">
                    <strong>全局检索</strong>
                    <button type="button" className="hc-quicksearch__close" onClick={onClose} aria-label="关闭">×</button>
                </div>
                <div className="hc-quicksearch__input-row">
                    <input
                        autoFocus
                        value={query}
                        maxLength={400}
                        placeholder="输入关键词，检索当前项目的资料片段"
                        onChange={(event) => setQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter') void submit()
                            if (event.key === 'Escape') onClose()
                        }}
                    />
                    <button type="button" disabled={loading || !query.trim()} onClick={() => void submit()}>
                        {loading ? '检索中…' : '检索'}
                    </button>
                </div>
                {error ? <div className="hc-quicksearch__error">{error}</div> : null}
                {lowConfidence ? <div className="hc-quicksearch__hint">相关片段较少，可尝试更具体的关键词</div> : null}
                <div className="hc-quicksearch__results">
                    {results.map((item) => (
                        <div key={`${item.id}-${item.chunkIndex ?? 0}`} className="hc-quicksearch__result">
                            <div className="hc-quicksearch__result-title">
                                <span>{item.title || item.filename || '未命名资料'}</span>
                                <span className="hc-quicksearch__score">{Math.round(item.score * 100)}%</span>
                            </div>
                            {item.snippet || item.content ? (
                                <p>{item.snippet || item.content}</p>
                            ) : null}
                        </div>
                    ))}
                    {!results.length && !loading && !error ? (
                        <div className="hc-quicksearch__empty">输入关键词开始检索知识库</div>
                    ) : null}
                </div>
            </div>
        </div>
    )
}

export default QuickSearch
