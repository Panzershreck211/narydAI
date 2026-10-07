import type { Availability, Criticality, FaultCategory, OrderStatus, OrderType, Priority, Role } from '../api/types'
import { localized, t } from '../i18n/lang'

export const ROLE: Record<Role, string> = localized({
  master: 'Мастер смены',
  executor: 'Исполнитель',
  manager: 'Руководитель',
  admin: 'Администратор',
})

export const STATUS: Record<OrderStatus, string> = localized({
  issued: 'Выдан',
  accepted: 'Принят',
  queued: 'В очереди',
  in_progress: 'В работе',
  paused: 'Приостановлен',
  completed: 'Исполнен',
  closed: 'Принят мастером',
  rejected: 'Отклонён',
  cancelled: 'Отменён',
})

export const ORDER_TYPE: Record<OrderType, string> = localized({ planned: 'Плановый', emergency: 'Аварийный' })

export const PRIORITY: Record<Priority, string> = localized({
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
  critical: 'Критический',
})

export const AVAILABILITY: Record<Availability, string> = localized({
  free: 'Свободен',
  busy: 'В работе',
  queued: 'Есть очередь',
  off_shift: 'Не на смене',
})

export const FAULT_CATEGORY: Record<FaultCategory, string> = localized({
  mechanical: 'Механика',
  electrical: 'Электрика',
  hydraulic: 'Гидравлика',
  pneumatic: 'Пневматика',
  instrumentation: 'КИПиА',
  lubrication: 'Смазка',
  other: 'Прочее',
})

export const CRITICALITY: Record<Criticality, string> = localized({
  A: 'A — останов производства',
  B: 'B — значимое',
  C: 'C — вспомогательное',
})

export const EVENT: Record<string, string> = localized({
  create: 'Наряд выдан',
  accept: 'Принят в работу',
  queue: 'Поставлен в очередь',
  reject: 'Отклонён',
  start: 'Начато исполнение',
  pause: 'Приостановлен',
  complete: 'Исполнено',
  approve: 'Работа принята',
  return: 'Возвращён на доработку',
  reassign: 'Переназначен',
  cancel: 'Отменён',
  update: 'Изменён',
  photo: 'Добавлены фото',
  reminder: 'ИИ: напоминание о сроке',
  overdue: 'ИИ: просрочка',
  risk: 'ИИ: риск просрочки',
  ai_check: 'ИИ-проверка',
})

/** Действия мастера, доступные из карточки (остальные — у исполнителя в мобильном приложении). */
export const MASTER_ACTIONS: Record<string, string> = localized({
  approve: 'Принять работу',
  return: 'Вернуть на доработку',
  reassign: 'Переназначить',
  cancel: 'Отменить наряд',
})

/** Строка журнала: «Возвращён на доработку → В работе»; без «→ статус», если он повторяет событие («Отменён»). */
export function eventTitle(action: string, toStatus: OrderStatus | null): string {
  const event = EVENT[action] ?? action
  if (!toStatus || action === 'create' || STATUS[toStatus] === event) return event
  return `${event} → ${STATUS[toStatus]}`
}

// «05.10 18:18» для обоих языков: локаль kk-KZ даёт «10-05», что читается как 10 мая
const dtf = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
export const fmtDateTime = (iso: string) => dtf.format(new Date(iso))

/** «через 1 ч 20 мин» / «просрочен на 15 мин» */
export function timeLeft(iso: string, now = Date.now()): string {
  const diff = Math.round((new Date(iso).getTime() - now) / 60_000)
  const abs = Math.abs(diff)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  const text = h ? t('{h} ч {m} мин', { h, m }) : t('{m} мин', { m })
  return diff >= 0 ? t('осталось {text}', { text }) : t('просрочен на {text}', { text })
}

/** Значение для <input type="datetime-local"> в локальном времени. */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
