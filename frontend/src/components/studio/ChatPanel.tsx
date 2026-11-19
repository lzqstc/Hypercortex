import { useCallback, useEffect, useRef, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type ChatMessage, type ChatSession } from './wikiApi'
import { EmptyState, formatTime, shortPath } from './ui'
import Markdown from './Markdown'

interface Props {
  projectId: string
  onOpenPage: (path: string) => void
}

const SUGGESTIONS = [
  '这些资料里反复出现的风险点是什么？给出来源。',
  '哪些结论之间存在矛盾？矛盾来自口径还是数据？',
  '如果要写一份 1 页决策摘要，最关键的 3 条依据是什么？',
]

const ChatPanel = ({ projectId, onOpenPage }: Props) => {
  const { notify, track } = useFeedback()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState('balanced')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const loadSessions = useCallback(async () => {
    try {
      const data = await wikiApi.sessions.list(projectId)
      setSessions(data.items)
      if (!activeId && data.items.length) setActiveId(data.items[0].id)
    } catch {
      setSessions([])
    }
  }, [projectId, activeId])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  useEffect(() => {
    if (!activeId) {
      setMessages([])
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const data = await wikiApi.sessions.get(projectId, activeId)
        if (!cancelled) setMessages(data.item.messages)
      } catch {
        if (!cancelled) setMessages([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId, activeId])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  const send = async () => {
    const value = question.trim()
    if (!value || sending) return
    setSending(true)
    const optimistic: ChatMessage = { role: 'user', content: value, createdAt: new Date().toISOString() }
    setMessages((current) => [...current, optimistic])
    setQuestion('')
    const result = await track(() => wikiApi.chat(projectId, value, activeId || undefined, mode), {
      error: '问答失败',
    })
    setSending(false)
    if (result) {
      setActiveId(result.sessionId)
      setMessages((current) => [...current.filter((item) => item !== optimistic), optimistic, result.message])
      void loadSessions()
    }
  }

  const newSession = async () => {
    const created = await track(() => wikiApi.sessions.create(projectId), { error: '创建会话失败' })
    if (created?.item) {
      setSessions((current) => [created.item, ...current])
      setActiveId(created.item.id)
      setMessages([])
    }
  }

  const removeSession = async (id: string) => {
    if (!window.confirm('删除该会话记录？')) return
    await track(() => wikiApi.sessions.remove(projectId, id), { success: '会话已删除', error: '删除失败' })
    setSessions((current) => current.filter((item) => item.id !== id))
    if (activeId === id) setActiveId('')
  }

  const saveAnswer = async (message: ChatMessage, question: string) => {
    const result = await track(
      () => wikiApi.saveChat(projectId, question, message.content, message.citations || []),
      { loading: '正在沉淀为页面', success: '已保存到 wiki', error: '保存失败' },
    )
    if (result?.path) notify('已生成问题页，可在知识页面里查看', 'success')
  }

  const lastQuestion = [...messages].reverse().find((message) => message.role === 'user')?.content || ''

  return (
    <div className="hc-studio__panel hc-studio__panel--chat">
      <aside className="hc-studio__chat-list">
        <div className="hc-studio__side-head">
          <strong>会话</strong>
          <button type="button" className="hc-studio__link" onClick={() => void newSession()}>
            + 新建
          </button>
        </div>
        {sessions.length === 0 ? (
          <p className="hc-studio__muted hc-studio__tree-empty">还没有会话</p>
        ) : (
          <ul className="hc-studio__history">
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  className={`hc-studio__history-item${activeId === session.id ? ' is-active' : ''}`}
                  onClick={() => setActiveId(session.id)}
                >
                  <span>{session.title}</span>
                  <em>
                    {session.messageCount} 条 · {formatTime(session.updatedAt)}
                  </em>
                </button>
                <button
                  type="button"
                  className="hc-studio__history-remove"
                  title="删除会话"
                  onClick={() => void removeSession(session.id)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="hc-studio__chat">
        <header className="hc-studio__chat-head">
          <div>
            <strong>基于 wiki 的问答</strong>
            <span className="hc-studio__muted">回答只依据页面内容，带 [n] 引用</span>
          </div>
          <select className="hc-studio__input is-compact" value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="fast">快速（4 页）</option>
            <option value="balanced">均衡（7 页）</option>
            <option value="deep">深入（10 页 + 图扩展）</option>
          </select>
        </header>

        <div className="hc-studio__messages" ref={scrollRef}>
          {messages.length === 0 ? (
            <EmptyState
              title="问一个能用现有页面回答的问题"
              hint="建议先确保「来源」里的资料已经编译成页面，否则问答会明确告诉你没有依据。"
              action={
                <div className="hc-studio__chips">
                  {SUGGESTIONS.map((item) => (
                    <button key={item} type="button" className="hc-studio__chip" onClick={() => setQuestion(item)}>
                      {item}
                    </button>
                  ))}
                </div>
              }
            />
          ) : (
            messages.map((message, index) => (
              <div key={`${message.createdAt}-${index}`} className={`hc-studio__msg is-${message.role}`}>
                <div className="hc-studio__msg-role">{message.role === 'user' ? '你' : 'HyperCortex'}</div>
                <div className="hc-studio__msg-body">
                  {message.role === 'assistant' ? (
                    <Markdown
                      content={message.content}
                      onWikiLink={(title) => notify(`在知识页面里搜索「${title}」`, 'info')}
                      onExternal={(url) => window.open(url, '_blank')}
                    />
                  ) : (
                    <p>{message.content}</p>
                  )}
                  {message.citations?.length ? (
                    <div className="hc-studio__citations">
                      {message.citations.map((citation) => (
                        <button
                          key={citation.index}
                          type="button"
                          className="hc-studio__citation"
                          onClick={() => onOpenPage(citation.path)}
                          title={shortPath(citation.path)}
                        >
                          <span>{citation.index}</span>
                          {citation.title}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {message.role === 'assistant' ? (
                    <div className="hc-studio__msg-actions">
                      <span className="hc-studio__muted">{message.model || ''}</span>
                      <button
                        type="button"
                        className="hc-studio__link"
                        onClick={() => void saveAnswer(message, lastQuestion)}
                      >
                        保存为页面
                      </button>
                      <button
                        type="button"
                        className="hc-studio__link"
                        onClick={() => {
                          void navigator.clipboard
                            .writeText(message.content)
                            .then(() => notify('已复制', 'success'))
                            .catch(() => notify('浏览器未授权剪贴板', 'error'))
                        }}
                      >
                        复制
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="hc-studio__composer">
          <textarea
            className="hc-studio__textarea"
            rows={2}
            placeholder="输入问题，Enter 发送，Shift + Enter 换行"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
          />
          <button type="button" className="hc-studio__btn is-primary" onClick={() => void send()} disabled={sending}>
            {sending ? '思考中…' : '发送'}
          </button>
        </div>
      </section>
    </div>
  )
}

export default ChatPanel
