import { useState } from 'react'

import { useDowntime, useRatings } from '../api/hooks'
import { ShiftStats } from '../components/ShiftStats'
import { Empty, ErrorBox, Spinner } from '../components/ui'
import { t } from '../i18n/lang'

// Подписи — ключи перевода
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

  const maxPoints = Math.max(1, ...(ratings.data ?? []).map((r) => r.points))
  const maxDown = Math.max(1, ...(downtime.data ?? []).map((r) => r.downtime_hours))

  return (
    <div>
      <div className="page-head">
        <h1>{t('Аналитика')}</h1>
        <div className="segmented segmented--sm">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              type="button"
              className={`segmented__item${days === p.days ? ' is-active' : ''}`}
              onClick={() => setDays(p.days)}
            >
              {t(p.label)}
            </button>
          ))}
        </div>
      </div>

      <ShiftStats />

      <div className="grid-2">
        <section className="panel">
          <h2>{t('Рейтинг исполнителей')}</h2>
          <p className="muted small">
            {t('Баллы = сложность (приоритет, аварийность, критичность оборудования) × своевременность × качество (оценка мастера и ИИ). −2 за каждый отказ.')}
          </p>
          {ratings.isPending && <Spinner />}
          {ratings.error && <ErrorBox error={ratings.error} onRetry={ratings.refetch} />}
          {ratings.data && (
            <div className="panel__scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t('Исполнитель')}</th>
                  <th className="num">{t('Закрыто')}</th>
                  <th className="num">{t('В срок')}</th>
                  <th className="num">{t('Качество')}</th>
                  <th className="num">{t('Отказы')}</th>
                  <th>{t('Баллы')}</th>
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
                    <td>
                      <Meter value={r.points} max={maxPoints} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>{t('Простои оборудования')}</h2>
          <p className="muted small">{t('Время от выдачи до исполнения нарядов с остановкой оборудования.')}</p>
          {downtime.isPending && <Spinner />}
          {downtime.error && <ErrorBox error={downtime.error} onRetry={downtime.refetch} />}
          {downtime.data?.length === 0 && <Empty>{t('Простоев за период нет')}</Empty>}
          {downtime.data && downtime.data.length > 0 && (
            <div className="panel__scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Оборудование')}</th>
                  <th className="num">{t('Нарядов')}</th>
                  <th>{t('Часы простоя')}</th>
                </tr>
              </thead>
              <tbody>
                {downtime.data.map((r) => (
                  <tr key={r.equipment_id}>
                    <td>
                      {r.equipment} {r.still_down && <span className="tag tag--red">{t('сейчас стоит')}</span>}
                      <div className="muted small">{r.inventory_number}</div>
                    </td>
                    <td className="num">{r.orders}</td>
                    <td>
                      <Meter value={r.downtime_hours} max={maxDown} tone="orange" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

/** Число + шкала относительно максимума в таблице. */
function Meter({ value, max, tone }: { value: number; max: number; tone?: 'orange' }) {
  return (
    <div className="meter">
      <b className="meter__value">{value}</b>
      <span className="meter__track">
        <span className={`meter__fill${tone ? ` meter__fill--${tone}` : ''}`} style={{ width: `${(value / max) * 100}%` }} />
      </span>
    </div>
  )
}
