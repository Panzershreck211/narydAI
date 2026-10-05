import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router'

import { useSetupStatus } from '../api/hooks'
import { useAuth } from '../auth/useAuth'

export function LoginPage() {
  const { user, login } = useAuth()
  const [form, setForm] = useState({ login: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const setup = useSetupStatus()

  if (user) return <Navigate to="/" replace />
  // Свежая установка без администратора — сразу на экран первой настройки
  if (setup.data?.needs_setup) return <Navigate to="/setup" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(form.login.trim(), form.password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка входа')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="login">
      <form className="login__card" onSubmit={submit}>
        <div className="brand brand--big">
          <span className="brand__logo">Н</span>
          <span>
            НарядAI
            <small>Панель мастера и руководства</small>
          </span>
        </div>
        <label className="field">
          <span className="field__label">Логин</span>
          <input
            value={form.login}
            onChange={(e) => setForm({ ...form, login: e.target.value })}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <label className="field">
          <span className="field__label">Пароль</span>
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <div className="error-box">{error}</div>}
        <button type="submit" className="btn btn--primary btn--block" disabled={pending}>
          {pending ? 'Вход…' : 'Войти'}
        </button>
      </form>
    </div>
  )
}
