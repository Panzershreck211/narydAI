import type { ReactNode } from 'react'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'

import type { Role } from './api/types'
import { useAuth } from './auth/useAuth'
import { Layout } from './components/Layout'
import { NAV } from './lib/nav'
import { Spinner } from './components/ui'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { BoardPage } from './pages/BoardPage'
import { LoginPage } from './pages/LoginPage'
import { OrdersPage } from './pages/OrdersPage'
import { ReferencesPage } from './pages/ReferencesPage'
import { SettingsPage } from './pages/SettingsPage'
import { SetupPage } from './pages/SetupPage'
import { UsersPage } from './pages/UsersPage'
import { t } from './i18n/lang'

const HOME: Record<Role, string> = { master: '/board', manager: '/analytics', admin: '/board', executor: '/login' }

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, error, retry, logout } = useAuth()
  if (loading) return <Spinner label={t('Подключение к серверу…')} />
  if (!user && error) {
    return (
      <div className="login">
        <div className="login__card">
          <b>{t('Нет связи с сервером')}</b>
          <span className="muted">{error}. {t('Вход сохранён — повторите, когда сервер будет доступен.')}</span>
          <button type="button" className="btn btn--primary btn--block" onClick={retry}>
            {t('Повторить')}
          </button>
          <button type="button" className="btn btn--ghost btn--block" onClick={logout}>
            {t('Войти под другим пользователем')}
          </button>
        </div>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}

/** Страница доступна, только если её роль есть в меню (RBAC на UI; API проверяет сам). */
function Guard({ path, children }: { path: string; children: ReactNode }) {
  const { user } = useAuth()
  const allowed = NAV.find((n) => n.to === path)?.roles.includes(user!.role)
  return allowed ? children : <Navigate to={HOME[user!.role]} replace />
}

function Home() {
  const { user } = useAuth()
  return <Navigate to={HOME[user!.role]} replace />
}

const page = (path: string, element: ReactNode) => ({
  path,
  element: <Guard path={path}>{element}</Guard>,
})

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/setup', element: <SetupPage /> },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Home /> },
      page('/board', <BoardPage />),
      page('/orders', <OrdersPage />),
      page('/analytics', <AnalyticsPage />),
      page('/users', <UsersPage />),
      page('/references', <ReferencesPage />),
      page('/settings', <SettingsPage />),
      { path: '*', element: <Home /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
