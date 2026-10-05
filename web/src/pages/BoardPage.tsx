import { useState } from 'react'

import { useBoard, useCounters, useExecutors, useReference, useUserMutations } from '../api/hooks'
import type { ExecutorAvailability } from '../api/types'
import { useUser } from '../auth/useAuth'
import { CreateOrderModal } from '../components/CreateOrderModal'
import { OrderCard } from '../components/OrderCard'
import { useToast } from '../components/useToast'
import { AvailabilityDot, ErrorBox, Spinner } from '../components/ui'
import { AVAILABILITY } from '../lib/labels'
import { Link } from 'react-router'

export function BoardPage() {
  const user = useUser()
  const [workshopId, setWorkshopId] = useState<number | undefined>()
  const [creating, setCreating] = useState(false)
  const board = useBoard(workshopId)
  const workshops = useReference('workshops')
  const canCreate = user.role === 'master' || user.role === 'admin'

  return (
    <div className="board-page">
      <div className="page-head">
        <h1>Доска нарядов</h1>
        <select
          className="select--inline"
          value={workshopId ?? ''}
          onChange={(e) => setWorkshopId(e.target.value ? Number(e.target.value) : undefined)}
          aria-label="Участок"
        >
          <option value="">Все участки</option>
          {workshops.data?.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <div className="page-head__spacer" />
        {canCreate && (
          <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
            + Выдать наряд
          </button>
        )}
      </div>

      <Counters />
      <ExecutorsStrip canToggle={canCreate} />

      {board.isPending && <Spinner />}
      {board.error && <ErrorBox error={board.error} onRetry={board.refetch} />}
      {board.data && (
        <div className="kanban">
          {board.data.map((col) => (
            <section key={col.key} className={`kanban__col kanban__col--${col.key}`}>
              <h2>
                {col.title} <span className="kanban__count">{col.orders.length}</span>
              </h2>
              <div className="kanban__list">
                {col.orders.map((o) => (
                  <OrderCard key={o.id} order={o} />
                ))}
                {col.orders.length === 0 && <div className="kanban__empty">—</div>}
              </div>
            </section>
          ))}
        </div>
      )}

      {creating && <CreateOrderModal onClose={() => setCreating(false)} />}
    </div>
  )
}

function Counters() {
  const { data } = useCounters()
  const items = [
    { key: 'issued', label: 'Выдано за смену', tone: '' },
    { key: 'in_progress', label: 'В работе', tone: 'amber' },
    { key: 'completed', label: 'Выполнено', tone: 'green' },
    { key: 'overdue', label: 'Просрочено', tone: 'red' },
    { key: 'equipment_down', label: 'Оборудование в простое', tone: 'orange' },
  ] as const
  return (
    <div className="stats">
      {items.map((i) => (
        <div key={i.key} className={`stat stat--${i.tone}`}>
          <span className="stat__value">{data ? data[i.key] : '–'}</span>
          <span className="stat__label">{i.label}</span>
        </div>
      ))}
    </div>
  )
}

function ExecutorsStrip({ canToggle }: { canToggle: boolean }) {
  const { data = [] } = useExecutors()
  const { setShift } = useUserMutations()
  const toast = useToast()
  const isAdmin = useUser().role === 'admin'

  const toggle = (x: ExecutorAvailability) =>
    setShift.mutate(
      { id: x.id, on_shift: x.availability === 'off_shift' },
      { onError: toast.error },
    )

  if (data.length === 0) {
    return (
      <div className="callout callout--info">
        <b>Исполнителей пока нет.</b> Зарегистрируйте слесарей, электриков и других сотрудников в разделе{' '}
        {isAdmin ? <Link to="/users">«Сотрудники»</Link> : '«Сотрудники» (это делает администратор)'} — после этого им
        можно выдавать наряды, а они войдут в мобильное приложение по табельному номеру и ПИН-коду.
      </div>
    )
  }

  return (
    <div className="people">
      <div className="people__legend">
        {(Object.keys(AVAILABILITY) as (keyof typeof AVAILABILITY)[]).map((a) => (
          <AvailabilityDot key={a} value={a} withLabel />
        ))}
      </div>
      <div className="people__list">
        {data.map((x) => (
          <div key={x.id} className={`person person--${x.availability}`}>
            <AvailabilityDot value={x.availability} />
            <span className="person__name">{x.fio.split(' ').slice(0, 2).join(' ')}</span>
            <span className="person__meta">
              {x.specialty}
              {x.active_orders + x.queued_orders > 0 && ` · ${x.active_orders}/${x.queued_orders}`}
            </span>
            {canToggle && (
              <button
                type="button"
                className="link person__shift"
                onClick={() => toggle(x)}
                title={x.availability === 'off_shift' ? 'Отметить на смене' : 'Снять со смены'}
              >
                {x.availability === 'off_shift' ? 'на смену' : 'со смены'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
