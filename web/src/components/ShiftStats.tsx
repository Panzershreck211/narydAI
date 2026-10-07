import { useCounters } from '../api/hooks'
import { t } from '../i18n/lang'

/** Счётчики текущей смены — на доске (по выбранному участку) и в аналитике (по всем). */
export function ShiftStats({ workshopId }: { workshopId?: number }) {
  const { data } = useCounters(workshopId)
  const items = [
    { key: 'issued', label: t('Выдано за смену'), tone: '' },
    { key: 'in_progress', label: t('В работе'), tone: 'amber' },
    { key: 'completed', label: t('Выполнено за смену'), tone: 'green' },
    { key: 'overdue', label: t('Просрочено сейчас'), tone: 'red' },
    { key: 'equipment_down', label: t('Оборудование в простое'), tone: 'orange' },
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
