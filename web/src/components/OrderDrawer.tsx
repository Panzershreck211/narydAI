import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'

import { useExecutors, useOrder, useOrderActions, useReference } from '../api/hooks'
import type { AIReport, OrderDetail, Priority } from '../api/types'
import { useUser } from '../auth/useAuth'
import { EVENT, fmtDateTime, MASTER_ACTIONS, ORDER_TYPE, PRIORITY, STATUS, timeLeft, toLocalInput } from '../lib/labels'
import { useToast } from './useToast'
import { AvailabilityDot, ErrorBox, Field, Modal, Spinner, StatusBadge } from './ui'

/** Боковая панель наряда. Открывается параметром ?order=ID с любой страницы. */
export function OrderDrawer() {
  const [params, setParams] = useSearchParams()
  const id = Number(params.get('order')) || null
  const close = () =>
    setParams((p) => {
      p.delete('order')
      return p
    })

  useEffect(() => {
    if (!id) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !document.querySelector('dialog[open]') && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!id) return null
  return (
    <>
      <div className="drawer-backdrop" onClick={close} />
      <aside className="drawer" aria-label="Карточка наряда">
        <DrawerContent id={id} onClose={close} />
      </aside>
    </>
  )
}

function DrawerContent({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: order, isPending, error, refetch } = useOrder(id)
  const [dialog, setDialog] = useState<string | null>(null)

  if (isPending) return <Spinner />
  if (error) return <ErrorBox error={error} onRetry={refetch} />

  const masterActions = order.allowed_actions.filter((a) => a in MASTER_ACTIONS)
  const editable = !['completed', 'closed', 'cancelled'].includes(order.status) && masterActions.length > 0

  return (
    <div className="drawer__content">
      <header className="drawer__head">
        <div>
          <div className="drawer__num">
            {order.type === 'emergency' && <span className="tag tag--red">АВАРИЙНЫЙ</span>} {order.number}
          </div>
          <StatusBadge status={order.status} />
          {order.is_overdue && <span className="tag tag--red">просрочен</span>}
        </div>
        <button type="button" className="icon-btn" aria-label="Закрыть" onClick={onClose}>
          ✕
        </button>
      </header>

      {masterActions.length > 0 && (
        <div className="drawer__actions">
          {masterActions.map((a) => (
            <button
              key={a}
              type="button"
              className={`btn btn--sm ${a === 'approve' ? 'btn--primary' : a === 'cancel' ? 'btn--danger' : ''}`}
              onClick={() => setDialog(a)}
            >
              {MASTER_ACTIONS[a]}
            </button>
          ))}
          {editable && (
            <button type="button" className="btn btn--sm btn--ghost" onClick={() => setDialog('edit')}>
              Изменить
            </button>
          )}
        </div>
      )}

      <section className="drawer__section">
        <p className="drawer__desc">{order.description}</p>
        <dl className="props">
          <dt>Тип</dt>
          <dd>{ORDER_TYPE[order.type]}</dd>
          <dt>Приоритет</dt>
          <dd>{PRIORITY[order.priority]}</dd>
          <dt>Участок</dt>
          <dd>{order.workshop.name}</dd>
          <dt>Оборудование</dt>
          <dd>
            {order.equipment ? `${order.equipment.name} (${order.equipment.inventory_number})` : '—'}
            {order.equipment_stopped && <span className="tag tag--amber">остановлено</span>}
          </dd>
          <dt>Исполнитель</dt>
          <dd>{order.executor?.fio ?? 'Бригада (не взят)'}</dd>
          <dt>Мастер</dt>
          <dd>{order.master.fio}</dd>
          <dt>Срок</dt>
          <dd className={order.is_overdue ? 'text-red' : undefined}>
            {fmtDateTime(order.deadline)}
            {!['completed', 'closed', 'cancelled'].includes(order.status) && ` · ${timeLeft(order.deadline)}`}
          </dd>
          <dt>Выдан</dt>
          <dd>{fmtDateTime(order.created_at)}</dd>
          {order.completed_at && (
            <>
              <dt>Исполнен</dt>
              <dd>{fmtDateTime(order.completed_at)}</dd>
            </>
          )}
          {order.master_score && (
            <>
              <dt>Оценка мастера</dt>
              <dd>{'★'.repeat(order.master_score)}</dd>
            </>
          )}
        </dl>
      </section>

      {order.work_report && (
        <section className="drawer__section">
          <h3>Отчёт исполнителя</h3>
          <p>{order.work_report}</p>
          {order.fault_code && (
            <p className="muted">
              Шифр: <b>{order.fault_code.code}</b> {order.fault_code.name}
            </p>
          )}
          {order.materials.length > 0 && (
            <table className="table table--compact">
              <tbody>
                {order.materials.map((m) => (
                  <tr key={m.id}>
                    <td>{m.material_name}</td>
                    <td className="num">
                      {m.quantity} {m.unit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {order.ai_report && <AiReportCard report={order.ai_report} orderId={order.id} />}

      <Photos order={order} />

      <section className="drawer__section">
        <h3>История</h3>
        <ol className="timeline">
          {[...order.events].reverse().map((e) => (
            <li key={e.id} className={e.user ? undefined : 'timeline__ai'}>
              <time>{fmtDateTime(e.timestamp)}</time>
              <div>
                <b>{e.to_status && e.action !== 'create' ? `${EVENT[e.action] ?? e.action} → ${STATUS[e.to_status]}` : EVENT[e.action] ?? e.action}</b>
                <div className="muted">
                  {e.user?.fio ?? 'ИИ-система'}
                  {e.reason && ` · ${e.reason}`}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {dialog && <ActionDialog order={order} action={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}

const VERDICT = { ok: 'Замечаний нет', needs_review: 'Нужна проверка', rejected: 'Есть нарушения' } as const

function AiReportCard({ report, orderId }: { report: AIReport; orderId: number }) {
  const { aiCheck } = useOrderActions(orderId)
  const toast = useToast()
  const issues = (report.checks ?? []).filter((c) => c.severity === 'warn' || c.severity === 'error')
  const notes = (report.checks ?? []).filter((c) => c.severity === 'info')
  return (
    <section className={`drawer__section ai ai--${report.verdict}`}>
      <div className="ai__head">
        <h3>✦ ИИ-проверка: {VERDICT[report.verdict]}</h3>
        <span className="ai__score">{report.score.toFixed(1)}/5</span>
      </div>
      <div className="muted">
        {report.source === 'rules+llm' ? 'Правила + LLM' : 'Правила'}
        {report.photo_score !== null && ` · качество фото ${report.photo_score.toFixed(1)}/5`}
      </div>
      {issues.length > 0 && (
        <ul className="ai__list">
          {issues.map((c, i) => (
            <li key={i} className={`sev sev--${c.severity}`}>
              {c.message}
            </li>
          ))}
        </ul>
      )}
      {notes.length > 0 && (
        <details>
          <summary>Подробнее ({notes.length})</summary>
          <ul className="ai__list">
            {notes.map((c, i) => (
              <li key={i} className="sev sev--info">
                {c.message}
              </li>
            ))}
          </ul>
        </details>
      )}
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        disabled={aiCheck.isPending}
        onClick={() => aiCheck.mutate(undefined, { onError: toast.error, onSuccess: () => toast.success('Проверка выполнена') })}
      >
        Перепроверить
      </button>
    </section>
  )
}

function Photos({ order }: { order: OrderDetail }) {
  const user = useUser()
  const { photos } = useOrderActions(order.id)
  const toast = useToast()
  const canAdd = user.role !== 'manager' && !['closed', 'cancelled'].includes(order.status)
  const before = order.photos.filter((p) => p.type === 'before')
  const after = order.photos.filter((p) => p.type === 'after')

  const strip = (title: string, list: typeof before, type?: 'before') => (
    <div>
      <h4>{title}</h4>
      <div className="photos">
        {list.map((p) => (
          <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
            <img src={p.url} alt={title} loading="lazy" />
          </a>
        ))}
        {type && canAdd && list.length < 5 && (
          <label className="photos__add">
            +
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              hidden
              onChange={(e) => {
                const files = [...(e.target.files ?? [])].slice(0, 5 - list.length)
                e.target.value = ''
                if (files.length) photos.mutate({ type, files }, { onError: toast.error })
              }}
            />
          </label>
        )}
        {!list.length && !(type && canAdd) && <span className="muted">нет</span>}
      </div>
    </div>
  )

  return (
    <section className="drawer__section">
      <h3>Фото {photos.isPending && <span className="muted">— загрузка…</span>}</h3>
      {strip('До', before, 'before')}
      {strip('После', after)}
    </section>
  )
}

function ActionDialog({ order, action, onClose }: { order: OrderDetail; action: string; onClose: () => void }) {
  const actions = useOrderActions(order.id)
  const executors = useExecutors()
  const brigades = useReference('brigades')
  const toast = useToast()

  const [reason, setReason] = useState('')
  const [score, setScore] = useState(5)
  const [assignee, setAssignee] = useState('')
  const [deadline, setDeadline] = useState(toLocalInput(new Date(order.deadline)))
  const [priority, setPriority] = useState<Priority>(order.priority)
  const [description, setDescription] = useState(order.description)
  const [stopped, setStopped] = useState(order.equipment_stopped)

  const pending = Object.values(actions).some((m) => m.isPending)
  const ok = (msg: string) => () => {
    toast.success(msg)
    onClose()
  }
  const opts = (msg: string) => ({ onSuccess: ok(msg), onError: toast.error })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    switch (action) {
      case 'approve':
        return actions.approve.mutate({ master_score: score, comment: reason || undefined }, opts('Работа принята'))
      case 'return':
      case 'cancel':
        return actions.action.mutate({ action, reason }, opts(action === 'return' ? 'Возвращён на доработку' : 'Наряд отменён'))
      case 'reassign': {
        const [kind, rawId] = assignee.split(':')
        const newDeadline = new Date(deadline)
        return actions.reassign.mutate(
          {
            executor_id: kind === 'u' ? Number(rawId) : null,
            brigade_id: kind === 'b' ? Number(rawId) : null,
            deadline: newDeadline > new Date() ? newDeadline.toISOString() : undefined,
          },
          opts('Наряд переназначен'),
        )
      }
      case 'edit':
        return actions.update.mutate(
          {
            description,
            priority,
            equipment_stopped: stopped,
            // срок шлём только при изменении: бэкенд при этом сбрасывает напоминания ИИ
            ...(deadline !== toLocalInput(new Date(order.deadline)) && { deadline: new Date(deadline).toISOString() }),
          },
          opts('Изменения сохранены'),
        )
    }
  }

  const title = action === 'edit' ? 'Изменить наряд' : MASTER_ACTIONS[action]
  const needsReason = action === 'return' || action === 'cancel'

  return (
    <Modal
      title={`${title} · ${order.number}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Отмена
          </button>
          <button
            type="submit"
            form="action-form"
            className={`btn ${action === 'cancel' ? 'btn--danger' : 'btn--primary'}`}
            disabled={pending || (needsReason && !reason.trim()) || (action === 'reassign' && !assignee)}
          >
            {title}
          </button>
        </>
      }
    >
      <form id="action-form" onSubmit={submit} className="form">
        {action === 'approve' && (
          <>
            {order.ai_report && order.ai_report.verdict !== 'ok' && (
              <div className="callout callout--warn">
                ИИ-проверка: {VERDICT[order.ai_report.verdict].toLowerCase()} — {order.ai_report.explanation}
              </div>
            )}
            <Field label="Оценка качества">
              <div className="stars" role="radiogroup">
                {[1, 2, 3, 4, 5].map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="radio"
                    aria-checked={score === s}
                    aria-label={`${s}`}
                    className={s <= score ? 'star star--on' : 'star'}
                    onClick={() => setScore(s)}
                  >
                    ★
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Комментарий">
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
            </Field>
          </>
        )}

        {needsReason && (
          <Field label="Причина">
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} required autoFocus />
          </Field>
        )}

        {action === 'reassign' && (
          <>
            <Field label="Новый исполнитель или бригада">
              <select value={assignee} onChange={(e) => setAssignee(e.target.value)} required>
                <option value="">— выберите —</option>
                <optgroup label="Исполнители">
                  {executors.data?.map((x) => (
                    <option key={x.id} value={`u:${x.id}`} disabled={x.id === order.executor?.id}>
                      {x.fio} · {x.specialty} · {x.availability === 'free' ? 'свободен' : x.availability === 'off_shift' ? 'не на смене' : `нарядов: ${x.active_orders + x.queued_orders}`}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Бригады">
                  {brigades.data?.map((b) => (
                    <option key={b.id} value={`b:${b.id}`}>
                      {b.name}
                    </option>
                  ))}
                </optgroup>
              </select>
            </Field>
            {executors.data && (
              <div className="avail-legend">
                {executors.data
                  .filter((x) => x.availability === 'free')
                  .map((x) => (
                    <button key={x.id} type="button" className="chip" onClick={() => setAssignee(`u:${x.id}`)}>
                      <AvailabilityDot value={x.availability} /> {x.fio.split(' ')[0]}
                    </button>
                  ))}
              </div>
            )}
            <Field label="Новый срок" hint="Оставьте прежним, если не меняется">
              <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </Field>
          </>
        )}

        {action === 'edit' && (
          <>
            <Field label="Описание">
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            </Field>
            <div className="form__row">
              <Field label="Приоритет">
                <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
                  {Object.entries(PRIORITY).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Срок">
                <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
              </Field>
            </div>
            <label className="check">
              <input type="checkbox" checked={stopped} onChange={(e) => setStopped(e.target.checked)} />
              Оборудование остановлено
            </label>
          </>
        )}
      </form>
    </Modal>
  )
}
