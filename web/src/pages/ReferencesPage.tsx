import { useState, type FormEvent } from 'react'

import { useReference, useRefMutations, type RefName } from '../api/hooks'
import { useToast } from '../components/useToast'
import { ErrorBox, Field, Modal, Spinner } from '../components/ui'
import { CRITICALITY, FAULT_CATEGORY } from '../lib/labels'

type Row = { id: number } & Record<string, unknown>
type Options = { value: string; label: string }[]

interface Column {
  key: string
  label: string
  kind?: 'text' | 'number' | 'select'
  options?: 'workshops' | Options
  optional?: boolean
}

const categories: Options = Object.entries(FAULT_CATEGORY).map(([value, label]) => ({ value, label }))
const criticality: Options = Object.entries(CRITICALITY).map(([value, label]) => ({ value, label }))

const TABS: { name: RefName; title: string; columns: Column[] }[] = [
  { name: 'workshops', title: 'Участки', columns: [{ key: 'name', label: 'Название' }] },
  {
    name: 'equipment',
    title: 'Оборудование',
    columns: [
      { key: 'name', label: 'Наименование' },
      { key: 'inventory_number', label: 'Инв. номер' },
      { key: 'workshop_id', label: 'Участок', kind: 'select', options: 'workshops' },
      { key: 'criticality', label: 'Критичность', kind: 'select', options: criticality },
    ],
  },
  {
    name: 'brigades',
    title: 'Бригады',
    columns: [
      { key: 'name', label: 'Название' },
      { key: 'workshop_id', label: 'Участок', kind: 'select', options: 'workshops', optional: true },
    ],
  },
  {
    name: 'fault-codes',
    title: 'Шифры неисправностей',
    columns: [
      { key: 'code', label: 'Шифр' },
      { key: 'name', label: 'Неисправность' },
      { key: 'category', label: 'Категория', kind: 'select', options: categories },
    ],
  },
  {
    name: 'materials',
    title: 'Материалы и запчасти',
    columns: [
      { key: 'name', label: 'Наименование' },
      { key: 'sku', label: 'Артикул', optional: true },
      { key: 'unit', label: 'Ед.' },
      { key: 'category', label: 'Категория', kind: 'select', options: categories },
      { key: 'max_per_order', label: 'Макс. на наряд', kind: 'number', optional: true },
    ],
  },
]

export function ReferencesPage() {
  const [tab, setTab] = useState(TABS[0].name)
  const current = TABS.find((t) => t.name === tab)!
  return (
    <div>
      <div className="page-head">
        <h1>Справочники</h1>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.name}
            type="button"
            role="tab"
            aria-selected={tab === t.name}
            className={`tabs__item${tab === t.name ? ' is-active' : ''}`}
            onClick={() => setTab(t.name)}
          >
            {t.title}
          </button>
        ))}
      </div>
      <RefTable key={current.name} {...current} />
    </div>
  )
}

function RefTable({ name, title, columns }: (typeof TABS)[number]) {
  const { data, isPending, error, refetch } = useReference(name)
  const workshops = useReference('workshops')
  const { remove } = useRefMutations(name)
  const toast = useToast()
  const [editing, setEditing] = useState<Row | 'new' | null>(null)
  const [search, setSearch] = useState('')

  const resolve = (c: Column) =>
    c.options === 'workshops' ? (workshops.data ?? []).map((w) => ({ value: String(w.id), label: w.name })) : c.options

  const display = (c: Column, v: unknown) => {
    if (v === null || v === undefined || v === '') return '—'
    const opts = resolve(c)
    return opts?.find((o) => o.value === String(v))?.label ?? String(v)
  }

  const rows = ((data ?? []) as unknown as Row[]).filter((r) =>
    !search.trim() ? true : columns.some((c) => String(r[c.key] ?? '').toLowerCase().includes(search.trim().toLowerCase())),
  )

  return (
    <>
      <div className="filters">
        <input type="search" placeholder={`Поиск: ${title.toLowerCase()}`} value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="page-head__spacer" />
        <button type="button" className="btn btn--primary" onClick={() => setEditing('new')}>
          + Добавить
        </button>
      </div>
      {isPending && <Spinner />}
      {error && <ErrorBox error={error} onRetry={refetch} />}
      {data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.key} className={c.kind === 'number' ? 'num' : undefined}>
                    {c.label}
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  {columns.map((c) => (
                    <td key={c.key} className={c.kind === 'number' ? 'num' : c.key === 'code' || c.key === 'inventory_number' ? 'mono' : undefined}>
                      {display(c, r[c.key])}
                    </td>
                  ))}
                  <td className="actions">
                    <button type="button" className="link" onClick={() => setEditing(r)}>
                      Изменить
                    </button>
                    <button
                      type="button"
                      className="link link--danger"
                      onClick={() =>
                        confirm('Удалить запись? Если она используется в нарядах, сервер откажет.') &&
                        remove.mutate(r.id, { onSuccess: () => toast.success('Удалено'), onError: toast.error })
                      }
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="empty">Записей нет</div>}
        </div>
      )}
      {editing && (
        <RefDialog
          name={name}
          title={title}
          columns={columns}
          row={editing === 'new' ? null : editing}
          resolve={resolve}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  )
}

function RefDialog({
  name,
  title,
  columns,
  row,
  resolve,
  onClose,
}: {
  name: RefName
  title: string
  columns: Column[]
  row: Row | null
  resolve: (c: Column) => Options | undefined
  onClose: () => void
}) {
  const { create, update } = useRefMutations(name)
  const toast = useToast()
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(columns.map((c) => [c.key, row?.[c.key] == null ? '' : String(row[c.key])])),
  )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body: Record<string, unknown> = {}
    for (const c of columns) {
      const v = values[c.key].trim()
      if (!v) body[c.key] = null
      else if (c.kind === 'number' || c.key.endsWith('_id')) body[c.key] = Number(v)
      else body[c.key] = v
    }
    const opts = { onSuccess: () => (toast.success('Сохранено'), onClose()), onError: toast.error }
    // Тип тела зависит от справочника — сервер проверит схему сам
    if (row) update.mutate({ id: row.id, ...body } as never, opts)
    else create.mutate(body as never, opts)
  }

  return (
    <Modal
      title={`${row ? 'Изменить' : 'Добавить'}: ${title.toLowerCase()}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" form="ref-form" className="btn btn--primary" disabled={create.isPending || update.isPending}>
            Сохранить
          </button>
        </>
      }
    >
      <form id="ref-form" className="form" onSubmit={submit}>
        {columns.map((c, i) => (
          <Field key={c.key} label={c.label + (c.optional ? ' (необязательно)' : '')}>
            {c.kind === 'select' ? (
              <select
                value={values[c.key]}
                onChange={(e) => setValues({ ...values, [c.key]: e.target.value })}
                required={!c.optional}
              >
                <option value="">—</option>
                {resolve(c)?.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={c.kind === 'number' ? 'number' : 'text'}
                step="any"
                min={c.kind === 'number' ? 0 : undefined}
                value={values[c.key]}
                onChange={(e) => setValues({ ...values, [c.key]: e.target.value })}
                required={!c.optional}
                autoFocus={i === 0}
              />
            )}
          </Field>
        ))}
      </form>
    </Modal>
  )
}
