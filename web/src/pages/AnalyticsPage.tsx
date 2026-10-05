import { useState } from 'react'

import { useCounters, useDowntime, useRatings } from '../api/hooks'
import { ErrorBox, Spinner } from '../components/ui'

const PERIODS = [
  { days: 7, label: '7 дней' },
  { days: 30, label: '30 дней' },
  { days: 90, label: 'Квартал' },
]

export function AnalyticsPage() {
  const [days, setDays] = useState(30)
  // Момент открытия страницы, округлённый до часа: стабильный ключ кэша, без Date.now() в рендере
  const [hourStart] = useState(() => Math.floor(Date.now() / 3600_000) * 3600_000)
  const from = new Date(hourStart - days * 86400_000).toISOString()
  const ratings = useRatings(from)
  const downtime = useDowntime(days)
  const counters = useCounters()

  const maxPoints = Math.max(1, ...(ratings.data ?? []).map((r) => r.points))
  const maxDown = Math.max(1, ...(downtime.data ?? []).map((r) => r.downtime_hours))

  return (
    <div>
      <div className="page-head">
        <h1>Аналитика</h1>
        <div className="segmented segmented--sm">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              type="button"
              className={`segmented__item${days === p.days ? ' is-active' : ''}`}
              onClick={() => setDays(p.days)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {counters.data && (
        <div className="stats">
          <div className="stat">
            <span className="stat__value">{counters.data.issued}</span>
            <span className="stat__label">Выдано за смену</span>
          </div>
          <div className="stat stat--green">
            <span className="stat__value">{counters.data.completed}</span>
            <span className="stat__label">Выполнено за смену</span>
          </div>
          <div className="stat stat--red">
            <span className="stat__value">{counters.data.overdue}</span>
            <span className="stat__label">Просрочено сейчас</span>
          </div>
          <div className="stat stat--orange">
            <span className="stat__value">{counters.data.equipment_down}</span>
            <span className="stat__label">Единиц в простое</span>
          </div>
        </div>
      )}

      <div className="grid-2">
        <section className="panel">
          <h2>Рейтинг исполнителей</h2>
          <p className="muted small">
            Баллы = сложность (приоритет, аварийность, критичность оборудования) × своевременность × качество
            (оценка мастера и ИИ). −2 за каждый отказ.
          </p>
          {ratings.isPending && <Spinner />}
          {ratings.error && <ErrorBox error={ratings.error} onRetry={ratings.refetch} />}
          {ratings.data && (
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Исполнитель</th>
                  <th className="num">Закрыто</th>
                  <th className="num">В срок</th>
                  <th className="num">Качество</th>
                  <th className="num">Отказы</th>
                  <th>Баллы</th>
                </tr>
              </thead>
              <tbody>
                {ratings.data.map((r) => (
                  <tr key={r.executor_id}>
                    <td className={`rank rank--${r.rank}`}>{r.rank}</td>
                    <td>
                      {r.fio}
                      <div className="muted small">{r.specialty}</div>
                    </td>
                    <td className="num">{r.closed}</td>
                    <td className="num">{r.closed ? `${r.on_time_pct}%` : '—'}</td>
                    <td className="num">{r.avg_quality?.toFixed(1) ?? '—'}</td>
                    <td className="num">{r.rejects || ''}</td>
                    <td className="bar-cell">
                      <span className="bar" style={{ width: `${(r.points / maxPoints) * 100}%` }} />
                      <b>{r.points}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <h2>Простои оборудования</h2>
          <p className="muted small">Время от выдачи до исполнения нарядов с остановкой оборудования.</p>
          {downtime.isPending && <Spinner />}
          {downtime.error && <ErrorBox error={downtime.error} onRetry={downtime.refetch} />}
          {downtime.data?.length === 0 && <div className="empty">Простоев за период нет</div>}
          {downtime.data && downtime.data.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Оборудование</th>
                  <th className="num">Нарядов</th>
                  <th>Часы простоя</th>
                </tr>
              </thead>
              <tbody>
                {downtime.data.map((r) => (
                  <tr key={r.equipment_id}>
                    <td>
                      {r.equipment} {r.still_down && <span className="tag tag--red">сейчас стоит</span>}
                      <div className="muted small">{r.inventory_number}</div>
                    </td>
                    <td className="num">{r.orders}</td>
                    <td className="bar-cell">
                      <span className="bar bar--orange" style={{ width: `${(r.downtime_hours / maxDown) * 100}%` }} />
                      <b>{r.downtime_hours}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  )
}
