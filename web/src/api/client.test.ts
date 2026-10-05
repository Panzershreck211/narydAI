import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError, setSessionExpiredHandler, tokens } from './client'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const headersOf = (init: RequestInit | undefined) => (init?.headers ?? {}) as Record<string, string>

describe('api client', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    localStorage.clear()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('подставляет Bearer-токен и собирает query с массивами', async () => {
    tokens.save({ access_token: 'A1', refresh_token: 'R1' })
    fetchMock.mockResolvedValueOnce(json(200, []))

    await api('/orders', { query: { status: ['issued', 'queued'], overdue: true, type: undefined, q: '' } })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/orders?status=issued&status=queued&overdue=true')
    expect(headersOf(init).Authorization).toBe('Bearer A1')
  })

  it('отдаёт detail-строку бэкенда как текст ошибки', async () => {
    fetchMock.mockResolvedValueOnce(json(409, { detail: 'Логин уже занят' }))
    await expect(api('/users', { body: {} })).rejects.toMatchObject({ status: 409, message: 'Логин уже занят' })
  })

  it('разбирает ошибки валидации FastAPI (422)', async () => {
    fetchMock.mockResolvedValueOnce(
      json(422, { detail: [{ loc: ['body', 'deadline'], msg: 'Value error, срок в прошлом' }] }),
    )
    await expect(api('/orders', { body: {} })).rejects.toThrow('срок в прошлом (deadline)')
  })

  it('при 401 обновляет токен и повторяет запрос', async () => {
    tokens.save({ access_token: 'old', refresh_token: 'R1' })
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(200, { access_token: 'new', refresh_token: 'R2' }))
      .mockResolvedValueOnce(json(200, { ok: true }))

    await expect(api('/auth/me')).resolves.toEqual({ ok: true })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh')
    expect(headersOf(fetchMock.mock.calls[2][1]).Authorization).toBe('Bearer new')
    expect(tokens.refresh).toBe('R2')
  })

  it('параллельные 401 делают только один refresh', async () => {
    tokens.save({ access_token: 'old', refresh_token: 'R1' })
    let refreshCalls = 0
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).endsWith('/auth/refresh')) {
        refreshCalls++
        return json(200, { access_token: 'new', refresh_token: 'R2' })
      }
      return headersOf(init).Authorization === 'Bearer new' ? json(200, { ok: true }) : json(401, {})
    })

    await Promise.all([api('/a'), api('/b'), api('/c')])
    expect(refreshCalls).toBe(1)
  })

  it('если refresh не удался — чистит токены и завершает сессию', async () => {
    tokens.save({ access_token: 'old', refresh_token: 'bad' })
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    fetchMock.mockResolvedValueOnce(json(401, {})).mockResolvedValueOnce(json(401, {}))

    await expect(api('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(expired).toHaveBeenCalledOnce()
    expect(tokens.access).toBeNull()
  })

  it('вход (auth: false) не пытается обновлять токен', async () => {
    fetchMock.mockResolvedValueOnce(json(401, { detail: 'Неверный логин или пароль' }))
    await expect(api('/auth/login', { body: {}, auth: false })).rejects.toThrow('Неверный логин или пароль')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('сетевая ошибка превращается в понятное сообщение', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api('/orders')).rejects.toMatchObject({ status: 0, message: 'Нет связи с сервером' })
  })

  it('FormData отправляется без Content-Type (его ставит браузер)', async () => {
    fetchMock.mockResolvedValueOnce(json(200, {}))
    await api('/orders/1/photos', { body: new FormData() })
    expect(headersOf(fetchMock.mock.calls[0][1])['Content-Type']).toBeUndefined()
  })
})
