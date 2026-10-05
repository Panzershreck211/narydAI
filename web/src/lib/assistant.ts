import { api, ApiError, tokens } from '../api/client'

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export type AssistantEvent =
  | { type: 'text'; text: string }
  | { type: 'tool'; name: string; label: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

/**
 * Стрим ответа помощника (Server-Sent Events поверх POST — EventSource умеет только GET).
 * Перед стримом дёргаем /assistant/status через api(): он при необходимости обновит токен.
 */
export async function streamChat(
  messages: ChatTurn[],
  onEvent: (e: AssistantEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const status = await api<{ configured: boolean }>('/assistant/status')
  if (!status.configured) throw new ApiError(503, 'ИИ-помощник не подключён')

  const res = await fetch('/api/v1/assistant/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokens.access}` },
    body: JSON.stringify({ messages }),
    signal,
  })
  if (!res.ok || !res.body) {
    let message = `Ошибка помощника (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* не JSON */
    }
    throw new ApiError(res.status, message)
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) onEvent(JSON.parse(line.slice(6)) as AssistantEvent)
      }
    }
  }
}

/** Номера нарядов в тексте ответа: НР-2026-000012 → id 12. */
export const ORDER_RE = /НР-\d{4}-(\d{6})/g
