// Типы ответов API — зеркало backend/app/schemas.

export type Role = 'master' | 'executor' | 'manager' | 'admin'
export type Shift = 'day' | 'night'
export type OrderType = 'planned' | 'emergency'
export type Priority = 'low' | 'medium' | 'high' | 'critical'
export type OrderStatus =
  | 'issued'
  | 'accepted'
  | 'queued'
  | 'in_progress'
  | 'paused'
  | 'completed'
  | 'closed'
  | 'rejected'
  | 'cancelled'
export type Availability = 'free' | 'busy' | 'queued' | 'off_shift'
export type FaultCategory =
  | 'mechanical'
  | 'electrical'
  | 'hydraulic'
  | 'pneumatic'
  | 'instrumentation'
  | 'lubrication'
  | 'other'
export type Criticality = 'A' | 'B' | 'C'

export interface User {
  id: number
  login: string
  fio: string
  role: Role
  specialty: string | null
  grade: number | null
  brigade_id: number | null
  shift: Shift | null
  is_active: boolean
  on_shift: boolean
  has_pin: boolean
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  user: User
}

export interface UserShort {
  id: number
  fio: string
  specialty?: string | null
  grade?: number | null
}

export interface ExecutorAvailability extends UserShort {
  brigade_id: number | null
  availability: Availability
  active_orders: number
  queued_orders: number
}

export interface Workshop {
  id: number
  name: string
}
export interface Equipment {
  id: number
  name: string
  inventory_number: string
  workshop_id: number
  criticality: Criticality
}
export interface Brigade {
  id: number
  name: string
  workshop_id: number | null
}
export interface FaultCode {
  id: number
  code: string
  name: string
  category: FaultCategory
}
export interface Material {
  id: number
  name: string
  sku: string | null
  unit: string
  category: FaultCategory
  max_per_order: number | null
}

export interface Order {
  id: number
  number: string | null
  type: OrderType
  description: string
  workshop: Workshop
  equipment: Equipment | null
  executor: UserShort | null
  brigade_id: number | null
  master: UserShort
  priority: Priority
  deadline: string
  status: OrderStatus
  is_overdue: boolean
  equipment_stopped: boolean
  created_at: string
  started_at: string | null
  completed_at: string | null
  closed_at: string | null
  master_score: number | null
  allowed_actions: string[]
}

export interface OrderEvent {
  id: number
  action: string
  from_status: OrderStatus | null
  to_status: OrderStatus | null
  reason: string | null
  timestamp: string
  user: UserShort | null
}

export interface OrderPhoto {
  id: number
  type: 'before' | 'after'
  url: string
  meta: Record<string, unknown> | null
  created_at: string
}

export interface AICheck {
  name: string
  severity: 'ok' | 'info' | 'warn' | 'error'
  message: string
}

export interface AIReport {
  id: number
  verdict: 'ok' | 'needs_review' | 'rejected'
  score: number
  photo_score: number | null
  explanation: string
  checks: AICheck[] | null
  source: string
  created_at: string
}

export interface OrderDetail extends Order {
  work_report: string | null
  fault_code: FaultCode | null
  events: OrderEvent[]
  photos: OrderPhoto[]
  materials: { id: number; material_id: number | null; material_name: string; quantity: number; unit: string }[]
  ai_report: AIReport | null
}

export interface BoardColumn {
  key: string
  title: string
  orders: Order[]
}

export interface ShiftCounters {
  issued: number
  completed: number
  overdue: number
  equipment_down: number
  in_progress: number
}

export interface RatingRow {
  rank: number
  executor_id: number
  fio: string
  specialty: string | null
  closed: number
  on_time_pct: number
  avg_quality: number | null
  rejects: number
  points: number
}

export interface DowntimeRow {
  equipment_id: number
  equipment: string
  inventory_number: string
  orders: number
  downtime_hours: number
  still_down: boolean
}

export interface Notification {
  id: number
  order_id: number | null
  kind: string
  title: string
  body: string
  is_emergency: boolean
  is_read: boolean
  created_at: string
}
