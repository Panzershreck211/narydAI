import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Order } from '../api/types'
import { OrderCard } from './OrderCard'

const base: Order = {
  id: 7,
  number: 'НР-2026-000007',
  type: 'planned',
  description: 'Грохот ГИЛ-52: замена сит',
  workshop: { id: 1, name: 'ДСФ' },
  equipment: { id: 2, name: 'Грохот ГИЛ-52', inventory_number: 'КМ-0220', workshop_id: 1, criticality: 'B' },
  executor: { id: 4, fio: 'Иванов Сергей Николаевич' },
  brigade_id: null,
  master: { id: 2, fio: 'Ахметов Е.С.' },
  priority: 'high',
  deadline: new Date(Date.now() + 3600_000).toISOString(),
  status: 'in_progress',
  is_overdue: false,
  equipment_stopped: false,
  created_at: new Date().toISOString(),
  started_at: null,
  completed_at: null,
  closed_at: null,
  master_score: null,
  allowed_actions: [],
}

function CurrentUrl() {
  const loc = useLocation()
  return <div data-testid="url">{loc.pathname + loc.search}</div>
}

const renderCard = (order: Order) =>
  render(
    <MemoryRouter initialEntries={['/board']}>
      <Routes>
        <Route
          path="/board"
          element={
            <>
              <OrderCard order={order} />
              <CurrentUrl />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )

describe('OrderCard', () => {
  afterEach(cleanup)

  it('показывает номер, статус, исполнителя и приоритет', () => {
    renderCard(base)
    expect(screen.getByText('НР-2026-000007')).toBeTruthy()
    expect(screen.getByText('В работе')).toBeTruthy()
    expect(screen.getByText('Иванов Сергей Николаевич')).toBeTruthy()
    expect(screen.getByText('Высокий')).toBeTruthy()
    expect(screen.queryByText('АВАРИЙНЫЙ')).toBeNull()
  })

  it('выделяет аварийный и просроченный наряд', () => {
    const { container } = renderCard({
      ...base,
      type: 'emergency',
      is_overdue: true,
      equipment_stopped: true,
      deadline: new Date(Date.now() - 20 * 60_000).toISOString(),
    })
    expect(screen.getByText('АВАРИЙНЫЙ')).toBeTruthy()
    expect(screen.getByText('простой')).toBeTruthy()
    expect(screen.getByText(/просрочен на/)).toBeTruthy()
    const card = container.querySelector('.ocard')!
    expect(card.className).toContain('ocard--emergency')
    expect(card.className).toContain('ocard--overdue')
  })

  it('наряд на бригаду без исполнителя', () => {
    renderCard({ ...base, executor: null, brigade_id: 1 })
    expect(screen.getByText('Бригада — ещё не взят')).toBeTruthy()
  })

  it('клик открывает карточку через ?order=ID', () => {
    renderCard(base)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByTestId('url').textContent).toBe('/board?order=7')
  })
})
