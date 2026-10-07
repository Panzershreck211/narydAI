import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'

import { api } from '../api/client'
import { useSetupStatus } from '../api/hooks'
import type { TokenPair } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Spinner } from '../components/ui'
import { t } from '../i18n/lang'
import { LangSwitch } from '../i18n/LangSwitch'

/**
 * Первый запуск: в системе ещё нет администратора. Человек сам создаёт его
 * здесь — без консоли и правки файлов. После этого экран закрывается навсегда.
 */
export function SetupPage() {
  const { user, acceptSession } = useAuth()
  const status = useSetupStatus()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [f, setF] = useState({ fio: '', login: '', password: '', password2: '', load_examples: true })
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // Сразу после настройки — следующий шаг: регистрация сотрудников
  if (user) return <Navigate to={status.data?.needs_setup === false ? '/' : '/users'} replace />
  if (status.isPending) return <Spinner label={t('Проверяю систему…')} />
  if (status.data && !status.data.needs_setup) return <Navigate to="/login" replace />

  const set = (k: 'fio' | 'login' | 'password' | 'password2') => (e: { target: { value: string } }) =>
    setF({ ...f, [k]: e.target.value })

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (f.password !== f.password2) return setError(t('Пароли не совпадают'))
    setPending(true)
    try {
      const pair = await api<TokenPair>('/setup', {
        auth: false,
        body: { fio: f.fio.trim(), login: f.login.trim(), password: f.password, load_examples: f.load_examples },
      })
      acceptSession(pair)
      navigate('/users', { replace: true })
      qc.invalidateQueries({ queryKey: ['setup'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Не удалось сохранить'))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="login">
      <LangSwitch />
      <form className="login__card login__card--wide" onSubmit={submit}>
        <div className="brand brand--big">
          <span className="brand__logo">Н</span>
          <span>
            {t('Добро пожаловать в НарядAI')}
            <small>{t('Первый запуск — создайте администратора системы')}</small>
          </span>
        </div>

        <ol className="setup-steps">
          <li className="is-active">{t('Администратор')}</li>
          <li>{t('Сотрудники и справочники')}</li>
          <li>{t('Выдача нарядов')}</li>
        </ol>

        <label className="field">
          <span className="field__label">{t('ФИО администратора')}</span>
          <input value={f.fio} onChange={set('fio')} required minLength={3} autoFocus placeholder={t('Иванов Иван Иванович')} />
        </label>
        <label className="field">
          <span className="field__label">{t('Логин для входа')}</span>
          <input
            value={f.login}
            onChange={set('login')}
            required
            minLength={3}
            pattern="[A-Za-z0-9_.\-]+"
            autoComplete="username"
            placeholder="ivanov"
          />
          <span className="field__hint">{t('Латинские буквы, цифры, точка, дефис')}</span>
        </label>
        <div className="form__row">
          <label className="field">
            <span className="field__label">{t('Пароль')}</span>
            <input type="password" value={f.password} onChange={set('password')} required minLength={8} autoComplete="new-password" />
            <span className="field__hint">{t('Не короче 8 символов')}</span>
          </label>
          <label className="field">
            <span className="field__label">{t('Пароль ещё раз')}</span>
            <input type="password" value={f.password2} onChange={set('password2')} required minLength={8} autoComplete="new-password" />
          </label>
        </div>
        <label className="check check--wrap">
          <input type="checkbox" checked={f.load_examples} onChange={(e) => setF({ ...f, load_examples: e.target.checked })} />
          <span>
            {t('Заполнить справочники примерами')}
            <small className="muted"> {t('— участки, оборудование, шифры неисправностей, материалы. Потом их можно изменить.')}</small>
          </span>
        </label>

        {error && <div className="error-box">{error}</div>}
        <button type="submit" className="btn btn--primary btn--block" disabled={pending}>
          {pending ? t('Создаю…') : t('Создать администратора и войти')}
        </button>
        <p className="muted small">
          {t('Этот экран доступен только один раз — пока в системе нет администратора. Дальше сотрудников регистрирует администратор в разделе «Сотрудники».')}
        </p>
      </form>
    </div>
  )
}
