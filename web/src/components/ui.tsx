import { useEffect, useRef, type ReactNode } from 'react'

import type { Availability, OrderStatus } from '../api/types'
import { AVAILABILITY, STATUS } from '../lib/labels'

export function StatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`badge badge--${status}`}>{STATUS[status]}</span>
}

export function AvailabilityDot({ value, withLabel = false }: { value: Availability; withLabel?: boolean }) {
  return (
    <span className="avail" title={AVAILABILITY[value]}>
      <span className={`avail__dot avail__dot--${value}`} />
      {withLabel && AVAILABILITY[value]}
    </span>
  )
}

export function Spinner({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="spinner" role="status">
      <span className="spinner__circle" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="error-box">
      {error instanceof Error ? error.message : 'Ошибка'}
      {onRetry && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

/** Модальное окно на <dialog>: фокус-ловушка и Esc из коробки. */
export function Modal({
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d || d.open) return
    d.showModal()
    // showModal() ставит фокус на первую кнопку (✕) и перебивает autoFocus React —
    // переносим фокус в первое поле формы
    d.querySelector<HTMLElement>(
      '.modal__body textarea, .modal__body input:not([type=checkbox]):not([type=file]):not([hidden]), .modal__body select',
    )?.focus()
  }, [])
  return (
    <dialog
      ref={ref}
      className={`modal${wide ? ' modal--wide' : ''}`}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <div className="modal__inner">
        <header className="modal__head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__foot">{footer}</footer>}
      </div>
    </dialog>
  )
}
