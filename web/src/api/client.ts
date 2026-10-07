import type { TokenPair } from './types'
import { getLang, t } from '../i18n/lang'

const PREFIX = '/api/v1'
const ACCESS = 'naryad.access'
const REFRESH = 'naryad.refresh'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// MVP: токены в localStorage. Для прода — refresh в httpOnly-cookie.
export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS)
  },
  get refresh() {
    return localStorage.getItem(REFRESH)
  },
  save(pair: Pick<TokenPair, 'access_token' | 'refresh_token'>) {
    localStorage.setItem(ACCESS, pair.access_token)
    localStorage.setItem(REFRESH, pair.refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}

let onSessionExpired: () => void = () => {}
export function setSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn
}

async function parseError(res: Response): Promise<ApiError> {
  let message = t('Ошибка сервера ({status})', { status: res.status })
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') message = body.detail
    else if (Array.isArray(body.detail) && body.detail.length) {
      const d = body.detail[0]
      const field = Array.isArray(d.loc) ? d.loc.at(-1) : ''
      message = `${String(d.msg).replace('Value error, ', '')}${field ? ` (${field})` : ''}`
    }
  } catch {
    /* тело не JSON */
  }
  return new ApiError(res.status, message)
}

// Один refresh на все параллельные 401
let refreshing: Promise<boolean> | null = null
function refreshTokens(): Promise<boolean> {
  refreshing ??= (async () => {
    const refresh = tokens.refresh
    if (!refresh) return false
    const res = await fetch(`${PREFIX}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
    if (!res.ok) return false
    tokens.save(await res.json())
    return true
  })().finally(() => {
    refreshing = null
  })
  return refreshing
}

type Query = Record<string, string | number | boolean | (string | number)[] | null | undefined>

export interface RequestOptions {
  method?: string
  body?: unknown
  query?: Query
  auth?: boolean
}

function buildUrl(path: string, query?: Query) {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => params.append(k, String(x)))
    else params.append(k, String(v))
  }
  const qs = params.toString()
  return `${PREFIX}${path}${qs ? `?${qs}` : ''}`
}

export async function api<T>(path: string, opts: RequestOptions = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {}
  const isForm = opts.body instanceof FormData
  if (opts.body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (opts.auth !== false && tokens.access) headers.Authorization = `Bearer ${tokens.access}`
  // сервер отдаёт свои тексты (ошибки, уведомления, журнал) на языке интерфейса
  headers['Accept-Language'] = getLang()

  let res: Response
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'),
      headers,
      body: opts.body === undefined ? undefined : isForm ? (opts.body as FormData) : JSON.stringify(opts.body),
    })
  } catch {
    throw new ApiError(0, t('Нет связи с сервером'))
  }

  if (res.status === 401 && opts.auth !== false && !retried) {
    if (await refreshTokens()) return api<T>(path, opts, true)
    tokens.clear()
    onSessionExpired()
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
