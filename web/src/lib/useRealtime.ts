import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { tokens } from '../api/client'
import { qk } from '../api/hooks'
import type { Notification } from '../api/types'
import { useToast } from '../components/useToast'
import { getLang } from '../i18n/lang'
import { useOpenOrder } from './useOpenOrder'

export type RealtimeState = 'connecting' | 'online' | 'offline'

/**
 * WebSocket /ws: на `order_changed` инвалидирует кэш нарядов (доска обновляется
 * без перезагрузки), на `notification` показывает тост. Переподключение с
 * экспоненциальной задержкой до 30 с.
 */
export function useRealtime(enabled: boolean): RealtimeState {
  const qc = useQueryClient()
  const toast = useToast()
  const [state, setState] = useState<RealtimeState>('connecting')
  // Ссылка на «открыть наряд» не должна пересоздавать соединение при каждом рендере
  const openOrder = useRef(useOpenOrder())

  useEffect(() => {
    if (!enabled) return
    let ws: WebSocket | null = null
    let attempt = 0
    let stopped = false
    let reconnect: ReturnType<typeof setTimeout> | undefined
    let ping: ReturnType<typeof setInterval> | undefined

    const connect = () => {
      const token = tokens.access
      if (!token || stopped) return
      setState('connecting')
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}&lang=${getLang()}`)

      ws.onopen = () => {
        attempt = 0
        setState('online')
        // Пока были офлайн, могли пропустить события
        qc.invalidateQueries({ queryKey: ['orders'] })
        ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('ping'), 25_000)
      }
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string)
        if (msg.type === 'order_changed') {
          qc.invalidateQueries({ queryKey: ['orders'] })
        } else if (msg.type === 'notification') {
          const n = msg.notification as Notification
          qc.invalidateQueries({ queryKey: qk.notifications })
          toast.push({
            kind: n.is_emergency ? 'emergency' : 'info',
            title: n.title,
            body: n.body,
            onClick: n.order_id ? () => openOrder.current(n.order_id!) : undefined,
          })
        }
      }
      ws.onclose = () => {
        clearInterval(ping)
        if (stopped) return
        setState('offline')
        reconnect = setTimeout(connect, Math.min(30_000, 1000 * 2 ** attempt++))
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(reconnect)
      clearInterval(ping)
      ws?.close()
    }
  }, [enabled, qc, toast])

  return state
}
