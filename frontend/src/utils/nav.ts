import type { KeyboardEvent, MouseEvent } from 'react'

type Navigate = (to: string) => void

export const pressable = (
    onClick: () => void,
    options?: { stopPropagation?: boolean },
) => ({
    role: 'button' as const,
    tabIndex: 0,
    style: { cursor: 'pointer' as const },
    onClick: (event: MouseEvent<HTMLElement>) => {
        if (options?.stopPropagation) event.stopPropagation()
        onClick()
    },
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            onClick()
        }
    },
})

export const navTo = (navigate: Navigate, path: string) => pressable(() => navigate(path))
