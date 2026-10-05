import { createContext, use, useMemo } from 'react'

export type ToastKind = 'info' | 'success' | 'error' | 'emergency'
export interface ToastInput {
  kind: ToastKind
  title: string
  body?: string
  onClick?: () => void
}
export type Push = (t: ToastInput) => void

export const ToastContext = createContext<Push>(() => {})

export function useToast() {
  const push = use(ToastContext)
  return useMemo(
    () => ({
      push,
      error: (e: unknown) => push({ kind: 'error', title: e instanceof Error ? e.message : String(e) }),
      success: (title: string) => push({ kind: 'success', title }),
    }),
    [push],
  )
}
