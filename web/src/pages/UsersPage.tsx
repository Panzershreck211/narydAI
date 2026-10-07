import { useMemo, useState, type FormEvent } from 'react'

import { useReference, useUserMutations, useUsers } from '../api/hooks'
import type { Role, Shift, User } from '../api/types'
import { useUser } from '../auth/useAuth'
import { useToast } from '../components/useToast'
import { ErrorBox, Field, Modal, Spinner } from '../components/ui'
import { ROLE } from '../lib/labels'
import { t } from '../i18n/lang'

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
      { onSuccess: () => toast.success(u.is_active ? t('Учётная запись заблокирована') : t('Учётная запись восстановлена')), onError: toast.error },
    )

  return (
    <div>
      <div className="page-head">
        <h1>{t('Сотрудники')}</h1>
        <div className="page-head__spacer" />
        <button type="button" className="btn btn--primary" onClick={() => setEditing('new')}>
          {t('+ Зарегистрировать')}
        </button>
      </div>

      <div className="filters">
        <input type="search" placeholder={t('ФИО или табельный номер')} value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value as Role | '')} aria-label={t('Роль')}>
          <option value="">{t('Все роли')}</option>
          {Object.entries(ROLE).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={showBlocked} onChange={(e) => setShowBlocked(e.target.checked)} />
          {t('Показать заблокированных')}
        </label>
      </div>

      {isPending && <Spinner />}
      {error && <ErrorBox error={error} onRetry={refetch} />}
      {data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('ФИО')}</th>
                <th>{t('Логин')}</th>
                <th>{t('Роль')}</th>
                <th>{t('Специальность')}</th>
                <th className="num">{t('Разряд')}</th>
                <th>{t('Бригада')}</th>
                <th>{t('Смена')}</th>
                <th>{t('ПИН')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} className={u.is_active ? undefined : 'row--muted'}>
                  <td>
                    {u.fio}
                    {!u.is_active && <span className="tag">{t('заблокирован')}</span>}
                  </td>
                  <td className="mono">{u.login}</td>
                  <td>{ROLE[u.role]}</td>
                  <td>{u.specialty ?? '—'}</td>
                  <td className="num">{u.grade ?? '—'}</td>
                  <td>{brigadeName(u.brigade_id)}</td>
                  <td>
                    {u.shift === 'day' ? t('Дневная') : u.shift === 'night' ? t('Ночная') : '—'}
                    {u.on_shift && <span className="tag tag--green">{t('на смене')}</span>}
                  </td>
                  <td>{u.has_pin ? '✓' : ''}</td>
                  <td className="actions">
                    <button type="button" className="link" onClick={() => setEditing(u)}>
                      {t('Изменить')}
                    </button>
                    <button type="button" className="link" onClick={() => setResetting(u)}>
                      {t('Пароль')}
                    </button>
                    {u.id !== me.id && (
                      <button type="button" className="link link--danger" onClick={() => toggleActive(u)}>
                        {u.is_active ? t('Блок.') : t('Разблок.')}
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
      // разряд есть только у исполнителей: при смене роли поле блокируется — и не сохраняется
      grade: f.role === 'executor' && f.grade ? Number(f.grade) : null,
      brigade_id: f.brigade_id ? Number(f.brigade_id) : null,
      shift: f.shift || null,
    }
    const opts = { onSuccess: () => (toast.success(user ? t('Сохранено') : t('Сотрудник зарегистрирован')), onClose()), onError: toast.error }
    if (user) update.mutate({ id: user.id, ...common }, opts)
    else create.mutate({ ...common, login: f.login.trim(), password: f.password, pin: f.pin || null }, opts)
  }

  const isExecutor = f.role === 'executor'
  return (
    <Modal
      title={user ? t('Сотрудник: {fio}', { fio: user.fio }) : t('Регистрация сотрудника')}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            {t('Отмена')}
          </button>
          <button type="submit" form="user-form" className="btn btn--primary" disabled={create.isPending || update.isPending}>
            {user ? t('Сохранить') : t('Зарегистрировать')}
          </button>
        </>
      }
    >
      <form id="user-form" className="form" onSubmit={submit}>
        <Field label={t('ФИО')}>
          <input value={f.fio} onChange={set('fio')} required minLength={3} autoFocus />
        </Field>
        {!user && (
          <div className="form__row">
            <Field label={t('Логин / табельный номер')} hint={t('латиница, цифры, . _ -')}>
              <input value={f.login} onChange={set('login')} required minLength={3} pattern="[A-Za-z0-9_.\-]+" />
            </Field>
            <Field label={t('Пароль')} hint={t('не короче 8 символов')}>
              <input type="password" value={f.password} onChange={set('password')} required minLength={8} autoComplete="new-password" />
            </Field>
          </div>
        )}
        <div className="form__row">
          <Field label={t('Роль')}>
            <select value={f.role} onChange={set('role')}>
              {Object.entries(ROLE).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('Специальность')}>
            <input value={f.specialty} onChange={set('specialty')} placeholder={t('Слесарь-ремонтник')} list="specialties" />
            <datalist id="specialties">
              {[t('Слесарь-ремонтник'), t('Электромонтёр'), t('Электрогазосварщик'), t('Слесарь КИПиА'), t('Машинист'), t('Мастер смены')].map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </Field>
        </div>
        <div className="form__row form__row--3">
          <Field label={t('Разряд')}>
            <select value={f.grade} onChange={set('grade')} disabled={!isExecutor}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5, 6].map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('Бригада')}>
            <select value={f.brigade_id} onChange={set('brigade_id')}>
              <option value="">—</option>
              {brigades.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('Смена')}>
            <select value={f.shift} onChange={set('shift')}>
              <option value="">—</option>
              <option value="day">{t('Дневная')}</option>
              <option value="night">{t('Ночная')}</option>
            </select>
          </Field>
        </div>
        {!user && isExecutor && (
          <Field label={t('ПИН для быстрого входа')} hint={t('4–6 цифр, можно задать позже')}>
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
      title={t('Сброс пароля: {fio}', { fio: user.fio })}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            {t('Отмена')}
          </button>
          <button type="submit" form="reset-form" className="btn btn--primary" disabled={resetPassword.isPending}>
            {t('Сохранить')}
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
            { onSuccess: () => (toast.success(t('Пароль изменён, блокировка ПИН снята')), onClose()), onError: toast.error },
          )
        }}
      >
        <Field label={t('Новый пароль')} hint={t('не короче 8 символов')}>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" autoFocus />
        </Field>
        <Field label={t('Новый ПИН (необязательно)')}>
          <input value={pin} onChange={(e) => setPin(e.target.value)} pattern="\d{4,6}" inputMode="numeric" autoComplete="off" />
        </Field>
      </form>
    </Modal>
  )
}
