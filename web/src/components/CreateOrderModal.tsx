import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { useCreateOrder, useExecutors, useReference } from '../api/hooks'
import type { OrderType, Priority } from '../api/types'
import { AVAILABILITY, PRIORITY, toLocalInput } from '../lib/labels'
import { useToast } from './useToast'
import { AvailabilityDot, Field, Modal } from './ui'
import { useOpenOrder } from '../lib/useOpenOrder'

const AVAIL_ORDER = { free: 0, queued: 1, busy: 2, off_shift: 3 } as const
const hoursFromNow = (h: number) => toLocalInput(new Date(Date.now() + h * 3600_000))

/** Конец текущей смены: 08:00 / 20:00 по местному времени браузера. */
function shiftEnd(): string {
  const d = new Date()
  const end = new Date(d)
  end.setMinutes(0, 0, 0)
  if (d.getHours() < 8) end.setHours(8)
  else if (d.getHours() < 20) end.setHours(20)
  else {
    end.setDate(end.getDate() + 1)
    end.setHours(8)
  }
  return toLocalInput(end)
}

/** Выдача наряда «за минуту»: всё на одном экране, Ctrl+Enter — выдать. */
export function CreateOrderModal({ onClose }: { onClose: () => void }) {
  const workshops = useReference('workshops')
  const equipment = useReference('equipment')
  const brigades = useReference('brigades')
  const executors = useExecutors()
  const create = useCreateOrder()
  const toast = useToast()
  const openOrder = useOpenOrder()

  const [type, setType] = useState<OrderType>('planned')
  const [description, setDescription] = useState('')
  const [workshopId, setWorkshopId] = useState<number | ''>('')
  const [equipmentId, setEquipmentId] = useState<number | ''>('')
  const [assignee, setAssignee] = useState('') // u:<id> | b:<id>
  const [priority, setPriority] = useState<Priority>('medium')
  const [deadline, setDeadline] = useState(hoursFromNow(4))
  const [stopped, setStopped] = useState(false)
  const [photos, setPhotos] = useState<File[]>([])

  const previews = useMemo(() => photos.map((f) => URL.createObjectURL(f)), [photos])
  useEffect(() => () => previews.forEach(URL.revokeObjectURL), [previews])

  const eqList = (equipment.data ?? []).filter((e) => e.workshop_id === workshopId)
  const sortedExecutors = [...(executors.data ?? [])].sort(
    (a, b) => AVAIL_ORDER[a.availability] - AVAIL_ORDER[b.availability] || a.fio.localeCompare(b.fio),
  )

  const setEmergency = (t: OrderType) => {
    setType(t)
    if (t === 'emergency') {
      setPriority('critical')
      setDeadline(hoursFromNow(2))
      setStopped(true)
    }
  }

  const valid = description.trim().length >= 5 && workshopId !== '' && assignee !== '' && deadline !== ''

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    if (!valid || create.isPending) return
    if (new Date(deadline) <= new Date()) {
      toast.push({ kind: 'error', title: 'Срок исполнения должен быть в будущем' })
      return
    }
    const [kind, rawId] = assignee.split(':')
    create.mutate(
      {
        order: {
          type,
          description: description.trim(),
          workshop_id: Number(workshopId),
          equipment_id: equipmentId === '' ? null : equipmentId,
          executor_id: kind === 'u' ? Number(rawId) : null,
          brigade_id: kind === 'b' ? Number(rawId) : null,
          priority,
          deadline: new Date(deadline).toISOString(),
          equipment_stopped: stopped,
        },
        photos,
      },
      {
        onSuccess: (order) => {
          toast.success(`Наряд ${order.number} выдан`)
          onClose()
          openOrder(order.id)
        },
        onError: toast.error,
      },
    )
  }

  return (
    <Modal
      title="Новый наряд"
      wide
      onClose={onClose}
      footer={
        <>
          <span className="muted kbd-hint">Ctrl + Enter</span>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Отмена
          </button>
          <button
            type="submit"
            form="create-order"
            className={`btn ${type === 'emergency' ? 'btn--danger' : 'btn--primary'}`}
            disabled={!valid || create.isPending}
          >
            {create.isPending ? 'Выдаю…' : type === 'emergency' ? 'Выдать аварийный наряд' : 'Выдать наряд'}
          </button>
        </>
      }
    >
      <form
        id="create-order"
        className="form"
        onSubmit={submit}
        onKeyDown={(e) => e.key === 'Enter' && (e.ctrlKey || e.metaKey) && submit()}
      >
        <div className="segmented" role="radiogroup" aria-label="Тип работ">
          {(['planned', 'emergency'] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={type === t}
              className={`segmented__item${type === t ? ' is-active' : ''}${t === 'emergency' ? ' segmented__item--red' : ''}`}
              onClick={() => setEmergency(t)}
            >
              {t === 'planned' ? 'Плановый' : '⚠ Аварийный'}
            </button>
          ))}
        </div>

        <Field label="Описание проблемы">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Что случилось, где, признаки неисправности"
            autoFocus
          />
        </Field>

        <div className="form__row">
          <Field label="Участок">
            <select
              value={workshopId}
              onChange={(e) => {
                setWorkshopId(e.target.value ? Number(e.target.value) : '')
                setEquipmentId('')
              }}
              required
            >
              <option value="">— выберите —</option>
              {workshops.data?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Оборудование">
            <select
              value={equipmentId}
              onChange={(e) => setEquipmentId(e.target.value ? Number(e.target.value) : '')}
              disabled={workshopId === ''}
            >
              <option value="">— не указано —</option>
              {eqList.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} · {e.inventory_number} · кат. {e.criticality}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Исполнитель">
          <div className="assignees">
            {sortedExecutors.map((x) => (
              <button
                key={x.id}
                type="button"
                className={`assignee${assignee === `u:${x.id}` ? ' is-active' : ''}`}
                onClick={() => setAssignee(`u:${x.id}`)}
                aria-label={`${x.fio}, ${AVAILABILITY[x.availability].toLowerCase()}`}
                title={`${AVAILABILITY[x.availability]} · в работе ${x.active_orders}, ждут ${x.queued_orders}`}
              >
                <AvailabilityDot value={x.availability} />
                <span className="assignee__name">{x.fio}</span>
                <span className="assignee__spec">
                  {x.specialty}
                  {x.grade ? `, ${x.grade} разр.` : ''}
                </span>
              </button>
            ))}
            {brigades.data?.map((b) => (
              <button
                key={`b${b.id}`}
                type="button"
                className={`assignee assignee--brigade${assignee === `b:${b.id}` ? ' is-active' : ''}`}
                onClick={() => setAssignee(`b:${b.id}`)}
              >
                <span className="assignee__name">👥 {b.name}</span>
                <span className="assignee__spec">возьмёт первый свободный</span>
              </button>
            ))}
          </div>
        </Field>

        <div className="form__row">
          <Field label="Приоритет">
            <div className="segmented segmented--sm">
              {(Object.keys(PRIORITY) as Priority[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`segmented__item${priority === p ? ' is-active' : ''}`}
                  onClick={() => setPriority(p)}
                >
                  {PRIORITY[p]}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Срок исполнения">
            <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} required />
            <div className="quick">
              {[1, 2, 4, 8].map((h) => (
                <button key={h} type="button" className="chip" onClick={() => setDeadline(hoursFromNow(h))}>
                  +{h} ч
                </button>
              ))}
              <button type="button" className="chip" onClick={() => setDeadline(shiftEnd())}>
                до конца смены
              </button>
            </div>
          </Field>
        </div>

        <label className="check">
          <input type="checkbox" checked={stopped} onChange={(e) => setStopped(e.target.checked)} />
          Оборудование остановлено (учитывается в простое)
        </label>

        <Field label={`Фото «до» (${photos.length}/5)`}>
          <div className="photos">
            {previews.map((src, i) => (
              <div key={src} className="photos__item">
                <img src={src} alt="" />
                <button
                  type="button"
                  className="photos__remove"
                  aria-label="Убрать фото"
                  onClick={() => setPhotos(photos.filter((_, j) => j !== i))}
                >
                  ✕
                </button>
              </div>
            ))}
            {photos.length < 5 && (
              <label className="photos__add">
                +
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  hidden
                  onChange={(e) => {
                    setPhotos([...photos, ...(e.target.files ?? [])].slice(0, 5))
                    e.target.value = ''
                  }}
                />
              </label>
            )}
          </div>
        </Field>
      </form>
    </Modal>
  )
}
