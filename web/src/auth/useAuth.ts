import { createContext, use } from 'react'

import type { Role, TokenPair, User } from '../api/types'

export interface AuthState {
  user: User | null
  loading: boolean
  /** Сервер недоступен при восстановлении сессии (токены при этом сохранены). */
  error: string | null
  login: (login: string, password: string) => Promise<void>
  /** Принять готовую пару токенов (после первоначальной настройки). */
  acceptSession: (pair: TokenPair) => void
  logout: () => void
  retry: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

/** Исполнители работают в мобильном приложении, панель — для остальных ролей. */
export const PANEL_ROLES: Role[] = ['master', 'manager', 'admin']

export function useAuth(): AuthState {
  const ctx = use(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

/** Текущий пользователь на защищённых страницах (там он всегда есть). */
export function useUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('useUser on public page')
  return user
}
