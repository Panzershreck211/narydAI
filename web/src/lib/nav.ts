import type { Role } from '../api/types'

interface NavItem {
  to: string
  label: string
  icon: string
  roles: Role[]
}

/** Меню панели и права доступа к страницам по ролям. Подписи — ключи перевода, см. t(). */
export const NAV: NavItem[] = [
  { to: '/board', label: 'Доска нарядов', icon: '▦', roles: ['master', 'manager', 'admin'] },
  { to: '/orders', label: 'Все наряды', icon: '☰', roles: ['master', 'manager', 'admin'] },
  { to: '/analytics', label: 'Аналитика', icon: '◔', roles: ['manager', 'master', 'admin'] },
  { to: '/users', label: 'Сотрудники', icon: '👤', roles: ['admin'] },
  { to: '/references', label: 'Справочники', icon: '☷', roles: ['admin'] },
  { to: '/settings', label: 'Настройки', icon: '⚙', roles: ['admin'] },
]
