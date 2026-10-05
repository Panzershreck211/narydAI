import { useEffect, useRef, useState } from 'react'

import { useNotifications, useReadNotification } from '../api/hooks'
import { fmtDateTime } from '../lib/labels'
import { useOpenOrder } from '../lib/useOpenOrder'

export function NotificationsBell() {
  const { data = [] } = useNotifications()
  const read = useReadNotification()
  const openOrder = useOpenOrder()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const unread = data.filter((n) => !n.is_read).length

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div className="bell" ref={ref}>
      <button
        type="button"
        className="icon-btn"
        aria-label={`Уведомления${unread ? `: ${unread} новых` : ''}`}
        onClick={() => setOpen(!open)}
      >
        🔔{unread > 0 && <span className="bell__count">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="bell__panel">
          <div className="bell__head">
            <b>Уведомления</b>
            {unread > 0 && (
              <button type="button" className="link" onClick={() => read.all.mutate()}>
                Прочитать все
              </button>
            )}
          </div>
          {data.length === 0 && <div className="empty">Уведомлений нет</div>}
          <ul>
            {data.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  className={`notif${n.is_read ? '' : ' notif--unread'}${n.is_emergency ? ' notif--emergency' : ''}`}
                  onClick={() => {
                    if (!n.is_read) read.one.mutate(n.id)
                    if (n.order_id) openOrder(n.order_id)
                    setOpen(false)
                  }}
                >
                  <span className="notif__title">{n.title}</span>
                  <span className="notif__body">{n.body}</span>
                  <time>{fmtDateTime(n.created_at)}</time>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
