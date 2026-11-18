import type { KeyboardEvent } from 'react'

type Navigate = (to: string) => void

export const navTo = (navigate: Navigate, path: string) => ({
  role: 'button' as const,
  tabIndex: 0,
  style: { cursor: 'pointer' as const },
  onClick: () => navigate(path),
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      navigate(path)
    }
  },
})
