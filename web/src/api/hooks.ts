import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  BoardColumn,
  Brigade,
  DowntimeRow,
  Equipment,
  ExecutorAvailability,
  FaultCode,
  Material,
  Notification,
  Order,
  OrderDetail,
  OrderStatus,
  OrderType,
  Priority,
  RatingRow,
  ShiftCounters,
  User,
  Workshop,
} from './types'

/** Ключи кэша. Всё, что связано с нарядами, начинается с 'orders' — инвалидируется одним вызовом. */
export const qk = {
  board: (workshopId?: number) => ['orders', 'board', workshopId ?? 'all'] as const,
  orders: (filters: OrderFilters) => ['orders', 'list', filters] as const,
  order: (id: number) => ['orders', 'detail', id] as const,
  counters: (workshopId?: number) => ['orders', 'counters', workshopId ?? 'all'] as const,
  executors: ['orders', 'executors'] as const,
  ratings: (from?: string, to?: string) => ['analytics', 'ratings', from, to] as const,
  downtime: (days: number) => ['analytics', 'downtime', days] as const,
  users: ['users'] as const,
  refs: (name: RefName) => ['refs', name] as const,
  notifications: ['notifications'] as const,
}

export function useInvalidateOrders() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: ['orders'] })
}

// ---------- справочники ----------

export type RefName = 'workshops' | 'equipment' | 'brigades' | 'fault-codes' | 'materials'
type RefMap = {
  workshops: Workshop
  equipment: Equipment
  brigades: Brigade
  'fault-codes': FaultCode
  materials: Material
}

export function useReference<N extends RefName>(name: N) {
  return useQuery({
    queryKey: qk.refs(name),
    queryFn: () => api<RefMap[N][]>(`/refs/${name}`),
    staleTime: 5 * 60_000,
  })
}

export function useRefMutations<N extends RefName>(name: N) {
  const qc = useQueryClient()
  const done = () => qc.invalidateQueries({ queryKey: qk.refs(name) })
  return {
    create: useMutation({
      mutationFn: (body: Omit<RefMap[N], 'id'>) => api<RefMap[N]>(`/refs/${name}`, { body }),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: RefMap[N]) => api<RefMap[N]>(`/refs/${name}/${id}`, { method: 'PUT', body }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/refs/${name}/${id}`, { method: 'DELETE' }),
      onSuccess: done,
    }),
  }
}

// ---------- наряды ----------

export interface OrderFilters {
  status?: OrderStatus[]
  type?: OrderType
  workshop_id?: number
  executor_id?: number
  overdue?: boolean
  created_from?: string
  created_to?: string
}

export const useBoard = (workshopId?: number) =>
  useQuery({
    queryKey: qk.board(workshopId),
    queryFn: () => api<BoardColumn[]>('/orders/board', { query: { workshop_id: workshopId } }),
    refetchInterval: 30_000, // страховка, основное обновление — по WebSocket
  })

export const useOrders = (filters: OrderFilters) =>
  useQuery({
    queryKey: qk.orders(filters),
    queryFn: () => api<Order[]>('/orders', { query: { ...filters, limit: 500 } }),
  })

export const useOrder = (id: number | null) =>
  useQuery({
    queryKey: qk.order(id ?? 0),
    queryFn: () => api<OrderDetail>(`/orders/${id}`),
    enabled: id !== null,
  })

/** Счётчики смены; с участком — только по нему (как и доска). */
export const useCounters = (workshopId?: number) =>
  useQuery({
    queryKey: qk.counters(workshopId),
    queryFn: () => api<ShiftCounters>('/dashboard/counters', { query: { workshop_id: workshopId } }),
    refetchInterval: 60_000,
  })

export const useExecutors = () =>
  useQuery({ queryKey: qk.executors, queryFn: () => api<ExecutorAvailability[]>('/users/executors/availability') })

export interface NewOrder {
  type: OrderType
  description: string
  workshop_id: number
  equipment_id: number | null
  executor_id: number | null
  brigade_id: number | null
  priority: Priority
  deadline: string
  equipment_stopped: boolean
}

export function useCreateOrder() {
  const invalidate = useInvalidateOrders()
  return useMutation({
    mutationFn: async ({ order, photos }: { order: NewOrder; photos: File[] }) => {
      const created = await api<OrderDetail>('/orders', { body: order })
      if (photos.length) await uploadPhotos(created.id, 'before', photos)
      return created
    },
    onSuccess: invalidate,
  })
}

export function uploadPhotos(orderId: number, type: 'before' | 'after', files: File[]) {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  return api<OrderDetail>(`/orders/${orderId}/photos`, { body: form, query: { type } })
}

/** Все действия мастера над нарядом: approve / return / cancel / reassign / edit / ai-check / photos. */
export function useOrderActions(id: number) {
  const qc = useQueryClient()
  const onSuccess = (data: OrderDetail) => {
    qc.setQueryData(qk.order(id), data)
    qc.invalidateQueries({ queryKey: ['orders'] })
  }
  return {
    action: useMutation({
      mutationFn: ({ action, reason }: { action: string; reason?: string }) =>
        api<OrderDetail>(`/orders/${id}/actions/${action}`, { body: { reason: reason ?? null } }),
      onSuccess,
    }),
    approve: useMutation({
      mutationFn: (body: { master_score: number; comment?: string }) =>
        api<OrderDetail>(`/orders/${id}/approve`, { body }),
      onSuccess,
    }),
    reassign: useMutation({
      mutationFn: (body: { executor_id?: number | null; brigade_id?: number | null; deadline?: string }) =>
        api<OrderDetail>(`/orders/${id}/reassign`, { body }),
      onSuccess,
    }),
    update: useMutation({
      mutationFn: (body: Partial<Pick<NewOrder, 'description' | 'priority' | 'deadline' | 'equipment_stopped'>>) =>
        api<OrderDetail>(`/orders/${id}`, { method: 'PATCH', body }),
      onSuccess,
    }),
    aiCheck: useMutation({
      mutationFn: () => api<OrderDetail>(`/orders/${id}/ai-check`, { method: 'POST' }),
      onSuccess,
    }),
    photos: useMutation({
      mutationFn: ({ type, files }: { type: 'before' | 'after'; files: File[] }) => uploadPhotos(id, type, files),
      onSuccess,
    }),
  }
}

// ---------- аналитика ----------

export const useRatings = (from?: string, to?: string) =>
  useQuery({
    queryKey: qk.ratings(from, to),
    queryFn: () => api<RatingRow[]>('/analytics/ratings', { query: { date_from: from, date_to: to } }),
  })

export const useDowntime = (days: number) =>
  useQuery({ queryKey: qk.downtime(days), queryFn: () => api<DowntimeRow[]>('/analytics/downtime', { query: { days } }) })

// ---------- пользователи ----------

export const useUsers = () =>
  useQuery({ queryKey: qk.users, queryFn: () => api<User[]>('/users') })

export function useUserMutations() {
  const qc = useQueryClient()
  const done = () => {
    qc.invalidateQueries({ queryKey: qk.users })
    qc.invalidateQueries({ queryKey: qk.executors })
  }
  return {
    create: useMutation({ mutationFn: (body: object) => api<User>('/users', { body }), onSuccess: done }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
        api<User>(`/users/${id}`, { method: 'PATCH', body }),
      onSuccess: done,
    }),
    resetPassword: useMutation({
      mutationFn: ({ id, password, pin }: { id: number; password: string; pin?: string }) =>
        api<void>(`/users/${id}/reset-password`, { body: { password, pin: pin || null } }),
    }),
    setShift: useMutation({
      mutationFn: ({ id, on_shift }: { id: number; on_shift: boolean }) =>
        api<User>(`/users/${id}/shift`, { method: 'PATCH', body: { on_shift } }),
      onSuccess: done,
    }),
  }
}

// ---------- уведомления ----------

export const useNotifications = () =>
  useQuery({ queryKey: qk.notifications, queryFn: () => api<Notification[]>('/notifications', { query: { limit: 50 } }) })

export function useReadNotification() {
  const qc = useQueryClient()
  const done = () => qc.invalidateQueries({ queryKey: qk.notifications })
  return {
    one: useMutation({ mutationFn: (id: number) => api<void>(`/notifications/${id}/read`, { method: 'POST' }), onSuccess: done }),
    all: useMutation({ mutationFn: () => api<void>('/notifications/read-all', { method: 'POST' }), onSuccess: done }),
  }
}

// ---------- первоначальная настройка ----------

export const useSetupStatus = () =>
  useQuery({
    queryKey: ['setup'],
    queryFn: () => api<{ needs_setup: boolean }>('/setup/status', { auth: false }),
    staleTime: 0,
  })
