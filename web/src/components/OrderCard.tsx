import type { Order } from '../api/types'
import { fmtDateTime, PRIORITY, timeLeft } from '../lib/labels'
import { StatusBadge } from './ui'
import { useOpenOrder } from '../lib/useOpenOrder'
import { t } from '../i18n/lang'

export function OrderCard({ order }: { order: Order }) {
  const open = useOpenOrder()
  const emergency = order.type === 'emergency'
  const classes = ['ocard', emergency && 'ocard--emergency', order.is_overdue && 'ocard--overdue']
    .filter(Boolean)
    .join(' ')

  return (
    <button type="button" className={classes} onClick={() => open(order.id)}>
      <div className="ocard__top">
        {emergency && <span className="tag tag--red">{t('АВАРИЙНЫЙ')}</span>}
        <span className="ocard__num">{order.number}</span>
        <StatusBadge status={order.status} />
      </div>
      <p className="ocard__desc">{order.description}</p>
      <div className="ocard__meta">
        {order.equipment?.name ?? order.workshop.name}
        {/* простой заканчивается приёмкой работы мастером — как в счётчике на бэкенде */}
        {order.equipment_stopped && order.status !== 'closed' && order.status !== 'cancelled' && (
          <span className="tag tag--amber">{t('простой')}</span>
        )}
      </div>
      <div className="ocard__bottom">
        <span className={order.is_overdue ? 'text-red' : undefined} title={fmtDateTime(order.deadline)}>
          ⏱ {order.status === 'closed' || order.status === 'completed' ? fmtDateTime(order.deadline) : timeLeft(order.deadline)}
        </span>
        <span className={`prio prio--${order.priority}`}>{PRIORITY[order.priority]}</span>
      </div>
      <div className="ocard__who">{order.executor?.fio ?? t('Бригада — ещё не взят')}</div>
    </button>
  )
}
