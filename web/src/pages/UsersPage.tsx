import { useMemo, useState, type FormEvent } from 'react'

import { useReference, useUserMutations, useUsers } from '../api/hooks'
import type { Role, Shift, User } from '../api/types'
import { useUser } from '../auth/useAuth'
import { useToast } from '../components/useToast'
import { ErrorBox, Field, Modal, Spinner } from '../components/ui'
import { ROLE } from '../lib/labels'

export function UsersPage() {
  const me = useUser()
  const { data, isPending, error, refetch } = useUsers()
  const brigades = useReference('brigades')
  const { update } = useUserMutations()
  const toast = useToast()
  const [role, setRole] = useState<Role | ''>('')
  const [search, setSearch] = useState('')
  const [showBlocked, setShowBlocked] = useState(false)
  const [editing, setEditing] = useState<User | 'new' | null>(null)
  const [resetting, setResetting] = useState<User | null>(null)

  const brigadeName = (id: number | null) => brigades.data?.find((b) => b.id === id)?.name ?? '—'

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (data ?? []).filter(
      (u) =>
        (showBlocked || u.is_active) &&
        (!role || u.role === role) &&
        (!q || u.fio.toLowerCase().includes(q) || u.login.toLowerCase().includes(q)),
    )
  }, [data, role, search, showBlocked])

  const toggleActive = (u: User) =>
    update.mutate(
      { id: u.id, is_active: !u.is_active },
      { onSuccess: () => toast.success(u.is_active ? 'Учётная запись заблокирована' : 'Учётная запись восстановлена'), onError: toast.error },
    )

  return (
    <div>
      <div className="page-head">
        <h1>Сотрудники</h1>
        <div className="page-head__spacer" />
        <button type="button" className="btn btn--primary" onClick={() => setEditing('new')}>
          + Зарегистрировать
        </button>
      </div>

      <div className="filters">
        <input type="search" placeholder="ФИО или табельный номер" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value as Role | '')} aria-label="Роль">
          <option value="">Все роли</option>
          {Object.entries(ROLE).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={showBlocked} onChange={(e) => setShowBlocked(e.target.checked)} />
          Показать заблокированных
        </label>
      </div>

      {isPending && <Spinner />}
      {error && <ErrorBox error={error} onRetry={refetch} />}
      {data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ФИО</th>
                <th>Логин</th>
                <th>Роль</th>
                <th>Специальность</th>
                <th className="num">Разряд</th>
                <th>Бригада</th>
                <th>Смена</th>
                <th>ПИН</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} className={u.is_active ? undefined : 'row--muted'}>
                  <td>
                    {u.fio}
                    {!u.is_active && <span className="tag">заблокирован</span>}
                  </td>
                  <td className="mono">{u.login}</td>
                  <td>{ROLE[u.role]}</td>
                  <td>{u.specialty ?? '—'}</td>
                  <td className="num">{u.grade ?? '—'}</td>
                  <td>{brigadeName(u.brigade_id)}</td>
                  <td>
                    {u.shift === 'day' ? 'Дневная' : u.shift === 'night' ? 'Ночная' : '—'}
                    {u.on_shift && <span className="tag tag--green">на смене</span>}
                  </td>
                  <td>{u.has_pin ? '✓' : ''}</td>
                  <td className="actions">
                    <button type="button" className="link" onClick={() => setEditing(u)}>
                      Изменить
                    </button>
                    <button type="button" className="link" onClick={() => setResetting(u)}>
                      Пароль
                    </button>
                    {u.id !== me.id && (
                      <button type="button" className="link link--danger" onClick={() => toggleActive(u)}>
                        {u.is_active ? 'Блок.' : 'Разблок.'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && <UserDialog user={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {resetting && <ResetDialog user={resetting} onClose={() => setResetting(null)} />}
    </div>
  )
}

function UserDialog({ user, onClose }: { user: User | null; onClose: () => void }) {
  const brigades = useReference('brigades')
  const { create, update } = useUserMutations()
  const toast = useToast()
  const [f, setF] = useState({
    login: user?.login ?? '',
    password: '',
    pin: '',
    fio: user?.fio ?? '',
    role: user?.role ?? ('executor' as Role),
    specialty: user?.specialty ?? '',
    grade: user?.grade?.toString() ?? '',
    brigade_id: user?.brigade_id?.toString() ?? '',
    shift: user?.shift ?? ('' as Shift | ''),
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const common = {
      fio: f.fio.trim(),
      role: f.role,
      specialty: f.specialty.trim() || null,
      grade: f.grade ? Number(f.grade) : null,
      brigade_id: f.brigade_id ? Number(f.brigade_id) : null,
      shift: f.shift || null,
    }
    const opts = { onSuccess: () => (toast.success(user ? 'Сохранено' : 'Сотрудник зарегистрирован'), onClose()), onError: toast.error }
    if (user) update.mutate({ id: user.id, ...common }, opts)
    else create.mutate({ ...common, login: f.login.trim(), password: f.password, pin: f.pin || null }, opts)
  }

  const isExecutor = f.role === 'executor'
  return (
    <Modal
      title={user ? `Сотрудник: ${user.fio}` : 'Регистрация сотрудника'}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" form="user-form" className="btn btn--primary" disabled={create.isPending || update.isPending}>
            {user ? 'Сохранить' : 'Зарегистрировать'}
          </button>
        </>
      }
    >
      <form id="user-form" className="form" onSubmit={submit}>
        <Field label="ФИО">
          <input value={f.fio} onChange={set('fio')} required minLength={3} autoFocus />
        </Field>
        {!user && (
          <div className="form__row">
            <Field label="Логин / табельный номер" hint="латиница, цифры, . _ -">
              <input value={f.login} onChange={set('login')} required minLength={3} pattern="[A-Za-z0-9_.\-]+" />
            </Field>
            <Field label="Пароль" hint="не короче 8 символов">
              <input type="password" value={f.password} onChange={set('password')} required minLength={8} autoComplete="new-password" />
            </Field>
          </div>
        )}
        <div className="form__row">
          <Field label="Роль">
            <select value={f.role} onChange={set('role')}>
              {Object.entries(ROLE).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Специальность">
            <input value={f.specialty} onChange={set('specialty')} placeholder="Слесарь-ремонтник" list="specialties" />
            <datalist id="specialties">
              {['Слесарь-ремонтник', 'Электромонтёр', 'Электрогазосварщик', 'Слесарь КИПиА', 'Машинист', 'Мастер смены'].map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </Field>
        </div>
        <div className="form__row form__row--3">
          <Field label="Разряд">
            <select value={f.grade} onChange={set('grade')} disabled={!isExecutor}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5, 6].map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Бригада">
            <select value={f.brigade_id} onChange={set('brigade_id')}>
              <option value="">—</option>
              {brigades.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Смена">
            <select value={f.shift} onChange={set('shift')}>
              <option value="">—</option>
              <option value="day">Дневная</option>
              <option value="night">Ночная</option>
            </select>
          </Field>
        </div>
        {!user && isExecutor && (
          <Field label="ПИН для быстрого входа" hint="4–6 цифр, можно задать позже">
            <input value={f.pin} onChange={set('pin')} pattern="\d{4,6}" inputMode="numeric" autoComplete="off" />
          </Field>
        )}
      </form>
    </Modal>
  )
}

function ResetDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const { resetPassword } = useUserMutations()
  const toast = useToast()
  const [password, setPassword] = useState('')
  const [pin, setPin] = useState('')
  return (
    <Modal
      title={`Сброс пароля: ${user.fio}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" form="reset-form" className="btn btn--primary" disabled={resetPassword.isPending}>
            Сохранить
          </button>
        </>
      }
    >
      <form
        id="reset-form"
        className="form"
        onSubmit={(e) => {
          e.preventDefault()
          resetPassword.mutate(
            { id: user.id, password, pin },
            { onSuccess: () => (toast.success('Пароль изменён, блокировка ПИН снята'), onClose()), onError: toast.error },
          )
        }}
      >
        <Field label="Новый пароль" hint="не короче 8 символов">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" autoFocus />
        </Field>
        <Field label="Новый ПИН (необязательно)">
          <input value={pin} onChange={(e) => setPin(e.target.value)} pattern="\d{4,6}" inputMode="numeric" autoComplete="off" />
        </Field>
      </form>
    </Modal>
  )
}
