import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { tokens } from '../api/client'
import { streamChat, type AssistantEvent } from './assistant'

const sse = (chunks: string[]) =>
  new Response(
    new ReadableStream({
      start(c) {
        const enc = new TextEncoder()
        chunks.forEach((ch) => c.enqueue(enc.encode(ch)))
        c.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )

describe('streamChat', () => {
  const fetchMock = vi.fn<typeof fetch>()
  beforeEach(() => {
    localStorage.clear()
    tokens.save({ access_token: 'A', refresh_token: 'R' })
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('собирает события, даже если они разрезаны на куски', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ configured: true }), { status: 200 }))
      .mockResolvedValueOnce(
        sse([
          'data: {"type":"tool","name":"find_orders","label":"Ищу наряды"}\n\ndata: {"type":"te',
          'xt","text":"Просрочен "}\n\n',
          'data: {"type":"text","text":"НР-2026-000012"}\n\ndata: {"type":"done"}\n\n',
        ]),
      )
    const events: AssistantEvent[] = []
    await streamChat([{ role: 'user', content: 'Что просрочено?' }], (e) => events.push(e))

    expect(events.map((e) => e.type)).toEqual(['tool', 'text', 'text', 'done'])
    const [, init] = fetchMock.mock.calls[1]
    expect(JSON.parse(init!.body as string).messages[0].content).toBe('Что просрочено?')
    expect((init!.headers as Record<string, string>).Authorization).toBe('Bearer A')
  })

  it('не подключён — понятная ошибка без запроса к чату', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ configured: false }), { status: 200 }))
    await expect(streamChat([{ role: 'user', content: 'x' }], () => {})).rejects.toThrow('не подключён')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('ошибка сервера показывает detail', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ configured: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Ключ ИИ недействителен' }), { status: 503 }))
    await expect(streamChat([{ role: 'user', content: 'x' }], () => {})).rejects.toThrow('Ключ ИИ недействителен')
  })
})
