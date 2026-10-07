import { createContext, createElement, Fragment, type ReactNode, useContext } from 'react'

import { KK } from './kk'

export type Lang = 'ru' | 'kk'
const KEY = 'naryad.lang'

function load(): Lang {
  try {
    return localStorage.getItem(KEY) === 'kk' ? 'kk' : 'ru'
  } catch {
    return 'ru'
  }
}

let current: Lang = load()

export const getLang = () => current

export function storeLang(lang: Lang) {
  current = lang
  try {
    localStorage.setItem(KEY, lang)
  } catch {
    /* приватный режим — язык просто не запомнится */
  }
  document.documentElement.lang = lang
}

type Params = Record<string, string | number>

/**
 * Перевод строки интерфейса. Ключ — русский текст (основной язык), подстановки — {name}.
 * Интерфейс при смене языка монтируется заново (LangProvider), поэтому t() можно звать
 * где угодно во время рендера, без хуков.
 */
export function t(ru: string, params?: Params): string {
  const text = current === 'kk' ? (KK[ru] ?? ru) : ru
  return params ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : text
}

/**
 * Фраза со ссылкой или выделением внутри: переводится целиком (в казахском другой порядок слов),
 * а элементы встают на места {name}. tRich('Откройте {site} и войдите', { site: <b>…</b> })
 */
export function tRich(ru: string, nodes: Record<string, ReactNode>): ReactNode[] {
  return t(ru)
    .split(/(\{\w+\})/)
    .map((part, i) => {
      const name = /^\{(\w+)\}$/.exec(part)?.[1]
      return createElement(Fragment, { key: i }, name && name in nodes ? nodes[name] : part)
    })
}

/** Словарь подписей (статусы, роли…): значения пишутся по-русски, читаются на текущем языке. */
export function localized<K extends string>(map: Record<K, string>): Record<K, string> {
  return new Proxy(map, {
    get: (target, key) => (typeof key === 'string' && key in target ? t(target[key as K]) : undefined),
  })
}

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: current,
  setLang: () => {},
})

export const useLang = () => useContext(LangContext)
