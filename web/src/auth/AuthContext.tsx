import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, ApiError, setSessionExpiredHandler, tokens } from '../api/client'
import type { TokenPair, User } from '../api/types'
import { AuthContext, PANEL_ROLES } from './useAuth'
import { t } from '../i18n/lang'

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => tokens.access !== null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const logout = useCallback(() => {
    tokens.clear()
    setUser(null)
    qc.clear()
  }, [qc])

  useEffect(() => {
    setSessionExpiredHandler(logout)
    if (!tokens.access) return
    api<User>('/auth/me')
      .then((u) => {
        setUser(u)
        setError(null)
      })
      .catch((e: unknown) => {
        // Разлогиниваем только если сервер отверг токен (401 после неудачного refresh —
        // это уже сделал api()). Сеть/5xx — временно: сессию сохраняем, показываем ошибку.
        if (e instanceof ApiError && e.status === 401) logout()
        else setError(e instanceof Error ? e.message : t('Сервер недоступен'))
      })
      .finally(() => setLoading(false))
  }, [logout, attempt])

  const retry = useCallback(() => {
    setLoading(true)
    setAttempt((n) => n + 1)
  }, [])

  const login = useCallback(async (login: string, password: string) => {
    const pair = await api<TokenPair>('/auth/login', { body: { login, password }, auth: false })
    if (!PANEL_ROLES.includes(pair.user.role)) {
      throw new Error(t('Исполнители работают в мобильном приложении НарядAI'))
    }
    tokens.save(pair)
    setError(null)
    setUser(pair.user)
  }, [])

  const acceptSession = useCallback((pair: TokenPair) => {
    tokens.save(pair)
    setError(null)
    setUser(pair.user)
  }, [])

  const value = useMemo(
    () => ({ user, loading, error, login, logout, retry, acceptSession }),
    [user, loading, error, login, logout, retry, acceptSession],
  )
  return <AuthContext value={value}>{children}</AuthContext>
}
