import { useMemo, useState } from 'react'

import { useExecutors, useOrders, useReference, type OrderFilters } from '../api/hooks'
import type { OrderStatus, OrderType } from '../api/types'
import { ErrorBox, Spinner, StatusBadge } from '../components/ui'
import { useOpenOrder } from '../lib/useOpenOrder'
import { fmtDateTime, ORDER_TYPE, PRIORITY, STATUS } from '../lib/labels'

/** Реестр нарядов с фильтрами и выгрузкой в CSV. */
export function OrdersPage() {
  const [status, setStatus] = useState<OrderStatus | ''>('')
  const [type, setType] = useState<OrderType | ''>('')
  const [workshopId, setWorkshopId] = useState('')
  const [executorId, setExecutorId] = useState('')
  const [overdue, setOverdue] = useState(false)
  const [search, setSearch] = useState('')

  const filters: OrderFilters = {
    status: status ? [status] : undefined,
    type: type || undefined,
    workshop_id: workshopId ? Number(workshopId) : undefined,
    executor_id: executorId ? Number(executorId) : undefined,
    overdue: overdue || undefined,
  }
  const { data, isPending, error, refetch } = useOrders(filters)
  const workshops = useReference('workshops')
  const executors = useExecutors()
  const open = useOpenOrder()

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = data ?? []
    if (!q) return list
    return list.filter((o) =>
      [o.number, o.description, o.equipment?.name, o.executor?.fio].some((s) => s?.toLowerCase().includes(q)),
    )
  }, [data, search])

  const exportCsv = () => {
    const header = ['Номер', 'Тип', 'Статус', 'Приоритет', 'Участок', 'Оборудование', 'Исполнитель', 'Срок', 'Выдан', 'Просрочен', 'Описание']
    const lines = rows.map((o) =>
      [
        o.number,
        ORDER_TYPE[o.type],
        STATUS[o.status],
        PRIORITY[o.priority],
        o.workshop.name,
        o.equipment?.name ?? '',
        o.executor?.fio ?? '',
        fmtDateTime(o.deadline),
        fmtDateTime(o.created_at),
        o.is_overdue ? 'да' : '',
        o.description,
      ]
        .map((v) => `"${String(v ?? '').replaceAll('"', '""')}"`)
        .join(';'),
    )
    // BOM — чтобы Excel открыл кириллицу
    const blob = new Blob(['﻿' + [header.join(';'), ...lines].join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `naryady_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div>
      <div className="page-head">
        <h1>Все наряды</h1>
        <div className="page-head__spacer" />
        <button type="button" className="btn btn--ghost" onClick={exportCsv} disabled={!rows.length}>
          Выгрузить CSV
        </button>
      </div>

      <div className="filters">
        <input type="search" placeholder="Поиск: номер, описание, оборудование, ФИО" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value as OrderStatus | '')} aria-label="Статус">
          <option value="">Все статусы</option>
          {Object.entries(STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value as OrderType | '')} aria-label="Тип">
          <option value="">Все типы</option>
          <option value="planned">Плановые</option>
          <option value="emergency">Аварийные</option>
        </select>
        <select value={workshopId} onChange={(e) => setWorkshopId(e.target.value)} aria-label="Участок">
          <option value="">Все участки</option>
          {workshops.data?.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <select value={executorId} onChange={(e) => setExecutorId(e.target.value)} aria-label="Исполнитель">
          <option value="">Все исполнители</option>
          {executors.data?.map((x) => (
            <option key={x.id} value={x.id}>
              {x.fio}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />
          Только просроченные
        </label>
      </div>

      {isPending && <Spinner />}
      {error && <ErrorBox error={error} onRetry={refetch} />}
      {data && (
        <div className="table-wrap">
          <table className="table table--hover">
            <thead>
              <tr>
                <th>Номер</th>
                <th>Статус</th>
                <th>Описание</th>
                <th>Оборудование</th>
                <th>Исполнитель</th>
                <th>Приоритет</th>
                <th>Срок</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id} onClick={() => open(o.id)} className={o.type === 'emergency' ? 'row--emergency' : undefined}>
                  <td className="nowrap">
                    {o.type === 'emergency' && <span className="tag tag--red">А</span>} {o.number}
                  </td>
                  <td>
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="cell-desc">{o.description}</td>
                  <td>{o.equipment?.name ?? o.workshop.name}</td>
                  <td>{o.executor?.fio ?? '—'}</td>
                  <td>
                    <span className={`prio prio--${o.priority}`}>{PRIORITY[o.priority]}</span>
                  </td>
                  <td className={`nowrap${o.is_overdue ? ' text-red' : ''}`}>{fmtDateTime(o.deadline)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="empty">Нарядов не найдено</div>}
        </div>
      )}
    </div>
  )
}
