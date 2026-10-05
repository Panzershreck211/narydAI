import { describe, expect, it } from 'vitest'

import { timeLeft, toLocalInput } from './labels'

describe('timeLeft', () => {
  const now = new Date('2026-10-05T10:00:00Z').getTime()

  it('показывает оставшееся время', () => {
    expect(timeLeft('2026-10-05T11:20:00Z', now)).toBe('осталось 1 ч 20 мин')
    expect(timeLeft('2026-10-05T10:05:00Z', now)).toBe('осталось 5 мин')
  })

  it('показывает просрочку', () => {
    expect(timeLeft('2026-10-05T09:45:00Z', now)).toBe('просрочен на 15 мин')
    expect(timeLeft('2026-10-05T07:30:00Z', now)).toBe('просрочен на 2 ч 30 мин')
  })
})

describe('toLocalInput', () => {
  it('форматирует под <input type="datetime-local">', () => {
    expect(toLocalInput(new Date(2026, 0, 3, 7, 5))).toBe('2026-01-03T07:05')
  })

  it('обратимо через new Date()', () => {
    const d = new Date(2026, 9, 5, 18, 42)
    expect(new Date(toLocalInput(d)).getTime()).toBe(d.getTime())
  })
})
