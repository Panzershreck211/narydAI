import { NavLink, Outlet } from 'react-router'

import { useAuth, useUser } from '../auth/useAuth'
import { ROLE } from '../lib/labels'
import { NAV } from '../lib/nav'
import { useRealtime } from '../lib/useRealtime'
import { AssistantChat } from './AssistantChat'
import { NotificationsBell } from './NotificationsBell'
import { OrderDrawer } from './OrderDrawer'
import { t } from '../i18n/lang'
import { LangSwitch } from '../i18n/LangSwitch'

export function Layout() {
  const user = useUser()
  const { logout } = useAuth()
  const realtime = useRealtime(true)

  return (
    <div className="shell">
      <nav className="sidebar" aria-label={t('Разделы')}>
        <div className="brand">
          <span className="brand__logo">Н</span>
          <span>
            НарядAI
            <small>{t('Костанайские минералы')}</small>
          </span>
        </div>
        <ul>
          {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
            <li key={n.to}>
              <NavLink to={n.to} className={({ isActive }) => `nav${isActive ? ' is-active' : ''}`}>
                <span className="nav__icon" aria-hidden>
                  {n.icon}
                </span>
                {t(n.label)}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="sidebar__foot">
          <span className={`live live--${realtime}`}>
            {realtime === 'online' ? t('онлайн') : realtime === 'connecting' ? t('подключение…') : t('нет связи')}
          </span>
        </div>
      </nav>

      <div className="main">
        <header className="topbar">
          <div className="topbar__spacer" />
          <LangSwitch />
          <NotificationsBell />
          <div className="me">
            <b>{user.fio}</b>
            <small>{ROLE[user.role]}</small>
          </div>
          <button type="button" className="btn btn--ghost btn--sm" onClick={logout}>
            {t('Выйти')}
          </button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>

      <OrderDrawer />
      <AssistantChat />
    </div>
  )
}
