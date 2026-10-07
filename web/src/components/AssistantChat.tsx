import { useQuery } from '@tanstack/react-query'
import { Fragment, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Link } from 'react-router'

import { api } from '../api/client'
import { useUser } from '../auth/useAuth'
import { ORDER_RE, streamChat, type ChatTurn } from '../lib/assistant'
import { useOpenOrder } from '../lib/useOpenOrder'
import { t, tRich } from '../i18n/lang'

// История — своя у каждого пользователя: после выхода мастера вошедший в том же браузере
// администратор не должен видеть чужую переписку
const storageKey = (userId: number) => `naryad.assistant.history.${userId}`
// Модели нужен недавний контекст, а не вся переписка — так запрос не упирается в лимиты сервера
const CONTEXT_TURNS = 20

// Подсказки — ключи перевода, переводятся при отрисовке
const SUGGESTIONS: Record<string, string[]> = {
  master: ['Что сейчас просрочено?', 'Кто из исполнителей свободен?', 'Сводка по смене', 'Есть аварийные наряды?'],
  manager: ['Сводка по смене', 'Топ-3 исполнителя за месяц', 'Какое оборудование чаще простаивает?', 'Что просрочено?'],
  admin: ['Как зарегистрировать сотрудника?', 'Как добавить оборудование?', 'Сводка по смене', 'Кто свободен?'],
}

function loadHistory(userId: number): ChatTurn[] {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey(userId)) ?? '[]') as ChatTurn[]
  } catch {
    return []
  }
}

function saveHistory(userId: number, turns: ChatTurn[]) {
  try {
    sessionStorage.setItem(storageKey(userId), JSON.stringify(turns.slice(-40)))
  } catch {
    /* приватный режим — просто не сохраняем */
  }
}

/** Мини-разметка ответа: **жирный**, списки «- », номера нарядов — кликабельные. */
function RichText({ text, onOrder }: { text: string; onOrder: (id: number) => void }) {
  const inline = (line: string, key: string): ReactNode[] =>
    line.split(/(\*\*[^*]+\*\*|НР-\d{4}-\d{6})/g).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) return <b key={`${key}-${i}`}>{part.slice(2, -2)}</b>
      const m = [...part.matchAll(ORDER_RE)][0]
      if (m && m[0] === part)
        return (
          <button key={`${key}-${i}`} type="button" className="link link--inline" onClick={() => onOrder(Number(m[1]))}>
            {part}
          </button>
        )
      return <Fragment key={`${key}-${i}`}>{part}</Fragment>
    })

  const blocks: ReactNode[] = []
  let list: ReactNode[] = []
  const flush = () => {
    if (list.length) blocks.push(<ul key={`ul${blocks.length}`}>{list}</ul>)
    list = []
  }
  text.split('\n').forEach((line, i) => {
    const bullet = line.match(/^\s*[-•*]\s+(.*)/)
    if (bullet) list.push(<li key={i}>{inline(bullet[1], `l${i}`)}</li>)
    else {
      flush()
      if (line.trim()) blocks.push(<p key={i}>{inline(line.replace(/^#+\s*/, ''), `p${i}`)}</p>)
    }
  })
  flush()
  return <>{blocks}</>
}

export function AssistantChat() {
  const user = useUser()
  const openOrder = useOpenOrder()
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<ChatTurn[]>(() => loadHistory(user.id))
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [activity, setActivity] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const status = useQuery({
    queryKey: ['assistant-status'],
    queryFn: () => api<{ configured: boolean }>('/assistant/status'),
    enabled: open,
    staleTime: 30_000,
  })

  useEffect(() => saveHistory(user.id, turns), [user.id, turns])
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [turns, activity, open])
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || streaming) return
    const history: ChatTurn[] = [...turns, { role: 'user', content: question }]
    setTurns([...history, { role: 'assistant', content: '' }])
    setDraft('')
    setError(null)
    setStreaming(true)
    setActivity(t('Думаю'))
    abort.current = new AbortController()

    const append = (chunk: string) =>
      setTurns((ts) => {
        const last = ts[ts.length - 1]
        return [...ts.slice(0, -1), { ...last, content: last.content + chunk }]
      })

    try {
      await streamChat(
        history.slice(-CONTEXT_TURNS),
        (e) => {
          if (e.type === 'text') {
            setActivity(null)
            append(e.text)
          } else if (e.type === 'tool') {
            setActivity(e.label)
            // текст до и после поиска данных — разными абзацами
            setTurns((ts) => {
              const last = ts[ts.length - 1]
              return last.content && !last.content.endsWith('\n')
                ? [...ts.slice(0, -1), { ...last, content: last.content + '\n\n' }]
                : ts
            })
          } else if (e.type === 'error') setError(e.message)
        },
        abort.current.signal,
      )
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) setError(e instanceof Error ? e.message : String(e))
    } finally {
      setStreaming(false)
      setActivity(null)
      // пустой ответ (ошибка до первого слова) не храним в истории
      setTurns((ts) => (ts[ts.length - 1]?.content.trim() ? ts : ts.slice(0, -1)))
      inputRef.current?.focus()
    }
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send(draft)
    }
  }

  const clear = () => {
    abort.current?.abort()
    setTurns([])
    setError(null)
  }

  if (!open) {
    return (
      <button type="button" className="assistant-fab" onClick={() => setOpen(true)} aria-label={t('Открыть ИИ-помощника')}>
        <span aria-hidden>✦</span> {t('Помощник')}
      </button>
    )
  }

  const notConfigured = status.data && !status.data.configured

  return (
    <section className="assistant" aria-label={t('ИИ-помощник')}>
      <header className="assistant__head">
        <div>
          <b>{t('✦ ИИ-помощник')}</b>
          <small>{t('Отвечает по данным НарядAI')}</small>
        </div>
        {turns.length > 0 && (
          <button type="button" className="link" onClick={clear} title={t('Начать заново')}>
            {t('Очистить')}
          </button>
        )}
        <button type="button" className="icon-btn" aria-label={t('Свернуть помощника')} onClick={() => setOpen(false)}>
          ✕
        </button>
      </header>

      <div className="assistant__list" ref={listRef}>
        {notConfigured ? (
          <div className="assistant__empty">
            <p>
              <b>{t('Помощник ещё не подключён.')}</b>
            </p>
            {user.role === 'admin' ? (
              <p>
                {tRich('Добавьте бесплатный ключ Gemini в разделе {link} — это займёт минуту.', {
                  link: (
                    <Link to="/settings" onClick={() => setOpen(false)}>
                      «{t('Настройки')}»
                    </Link>
                  ),
                })}
              </p>
            ) : (
              <p>{t('Попросите администратора добавить ключ Gemini в разделе «Настройки».')}</p>
            )}
          </div>
        ) : turns.length === 0 ? (
          <div className="assistant__empty">
            <p>{t('Спросите о нарядах, исполнителях, простоях или о том, как что-то сделать в системе.')}</p>
            <div className="assistant__suggest">
              {(SUGGESTIONS[user.role] ?? SUGGESTIONS.master).map((s) => t(s)).map((s) => (
                <button key={s} type="button" className="chip" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn, i) => (
            <div key={i} className={`bubble bubble--${turn.role}`}>
              {turn.role === 'assistant' ? <RichText text={turn.content} onOrder={openOrder} /> : turn.content}
            </div>
          ))
        )}
        {activity && (
          <div className="assistant__activity" role="status">
            <span className="spinner__circle" /> {activity}…
          </div>
        )}
        {error && <div className="error-box">{error}</div>}
      </div>

      <form
        className="assistant__input"
        onSubmit={(e) => {
          e.preventDefault()
          void send(draft)
        }}
      >
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          maxLength={4000}
          placeholder={notConfigured ? t('Помощник не подключён') : t('Спросите… (Enter — отправить)')}
          disabled={notConfigured}
          aria-label={t('Вопрос помощнику')}
        />
        {streaming ? (
          <button type="button" className="btn btn--ghost" onClick={() => abort.current?.abort()}>
            {t('Стоп')}
          </button>
        ) : (
          <button type="submit" className="btn btn--primary" disabled={!draft.trim() || notConfigured}>
            ➤
          </button>
        )}
      </form>
    </section>
  )
}
