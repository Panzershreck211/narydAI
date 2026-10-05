import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { ToastContext, type Push, type ToastKind } from './useToast'

interface Toast {
  id: number
  kind: ToastKind
  title: string
  body?: string
  onClick?: () => void
}

let seq = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])

  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), [])

  const push = useCallback<Push>(
    (t) => {
      const id = ++seq
      setItems((xs) => [...xs.slice(-4), { ...t, id }])
      // Аварийные висят дольше
      setTimeout(() => dismiss(id), t.kind === 'emergency' ? 15_000 : 5_000)
    },
    [dismiss],
  )

  const value = useMemo(() => push, [push])
  return (
    <ToastContext value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`toast toast--${t.kind}`}
            onClick={() => {
              t.onClick?.()
              dismiss(t.id)
            }}
          >
            <strong>{t.title}</strong>
            {t.body && <span>{t.body}</span>}
          </button>
        ))}
      </div>
    </ToastContext>
  )
}
