import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

type Tone = 'info' | 'success' | 'error'

interface ToastItem {
  id: number
  message: string
  tone: Tone
}

interface TrackOptions {
  loading?: string
  success?: string
  error?: string
}

interface FeedbackContextValue {
  notify: (message: string, tone?: Tone) => void
  track: <T>(task: () => Promise<T>, options?: TrackOptions) => Promise<T | null>
}

const FeedbackContext = createContext<FeedbackContextValue | null>(null)

export const FeedbackProvider = ({ children }: { children: ReactNode }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [pending, setPending] = useState(0)
  const nextId = useRef(0)

  const notify = useCallback((message: string, tone: Tone = 'info') => {
    const id = ++nextId.current
    setToasts((current) => [...current.slice(-3), { id, message, tone }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 2800)
  }, [])

  const track = useCallback(
    async <T,>(task: () => Promise<T>, options?: TrackOptions): Promise<T | null> => {
      setPending((value) => value + 1)
      if (options?.loading) notify(options.loading, 'info')
      try {
        const result = await task()
        if (options?.success) notify(options.success, 'success')
        return result
      } catch (error) {
        const message = error instanceof Error ? error.message : '操作失败'
        notify(options?.error || message, 'error')
        return null
      } finally {
        setPending((value) => Math.max(0, value - 1))
      }
    },
    [notify],
  )

  const value = useMemo(() => ({ notify, track }), [notify, track])

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      {pending > 0 && <div className="hc-progress-bar" />}
      <div className="hc-toast-viewport" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`hc-toast hc-toast--${toast.tone}`} role="status">
            <span className="hc-toast__dot" />
            <span>{toast.message}</span>
          </div>
        ))}
      </div>
    </FeedbackContext.Provider>
  )
}

export const useFeedback = () => {
  const context = useContext(FeedbackContext)
  if (!context) {
    throw new Error('useFeedback 必须在 FeedbackProvider 中使用')
  }
  return context
}
