import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { tokens } from '../api/client'
import { AuthProvider } from './AuthContext'
import { useAuth } from './useAuth'

function Probe() {
  const { user, loading, error } = useAuth()
  return <div data-testid="state">{loading ? 'loading' : user ? `user:${user.login}` : error ? `error:${error}` : 'anon'}</div>
}

const renderAuth = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  )

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status })

describe('AuthProvider: восстановление сессии', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    localStorage.clear()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('без токена — сразу аноним, без запросов', () => {
    renderAuth()
    expect(screen.getByTestId('state').textContent).toBe('anon')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('с токеном — подтягивает пользователя', async () => {
    tokens.save({ access_token: 'A', refresh_token: 'R' })
    fetchMock.mockResolvedValue(json(200, { id: 1, login: 'master1', role: 'master' }))
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('user:master1'))
  })

  it('сервер недоступен — сессия НЕ теряется', async () => {
    tokens.save({ access_token: 'A', refresh_token: 'R' })
    fetchMock.mockResolvedValue(json(502, {}))
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toMatch(/^error:/))
    expect(tokens.access).toBe('A')
  })

  it('токен отозван (401 и refresh не прошёл) — выход', async () => {
    tokens.save({ access_token: 'A', refresh_token: 'R' })
    fetchMock.mockResolvedValue(json(401, {}))
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('anon'))
    expect(tokens.access).toBeNull()
  })
})
