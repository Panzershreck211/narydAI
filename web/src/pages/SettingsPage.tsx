import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import { useToast } from '../components/useToast'
import { ErrorBox, Field, Spinner } from '../components/ui'

interface AssistantSettings {
  configured: boolean
  source: 'panel' | 'env' | null
  key_hint: string | null
  model: string
}

/** Настройки системы, которые администратор меняет без правки файлов. */
export function SettingsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [key, setKey] = useState('')
  const settings = useQuery({
    queryKey: ['settings', 'assistant'],
    queryFn: () => api<AssistantSettings>('/settings/assistant'),
  })
  const done = () => {
    qc.invalidateQueries({ queryKey: ['settings', 'assistant'] })
    qc.invalidateQueries({ queryKey: ['assistant-status'] })
  }
  const save = useMutation({
    mutationFn: (api_key: string) => api<AssistantSettings>('/settings/assistant', { method: 'PUT', body: { api_key } }),
    onSuccess: () => {
      setKey('')
      done()
      toast.success('Ключ проверен и сохранён — помощник готов')
    },
    onError: toast.error,
  })
  const remove = useMutation({
    mutationFn: () => api<void>('/settings/assistant', { method: 'DELETE' }),
    onSuccess: () => {
      done()
      toast.success('Ключ удалён')
    },
    onError: toast.error,
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (key.trim()) save.mutate(key.trim())
  }

  const s = settings.data
  return (
    <div className="settings">
      <div className="page-head">
        <h1>Настройки</h1>
      </div>

      <section className="panel">
        <h2>✦ ИИ-помощник и ИИ-проверка нарядов</h2>
        <p className="muted">
          Помощник отвечает на вопросы в чате (кнопка «Помощник» внизу справа), а ИИ дополнительно проверяет смысл
          отчётов о выполненных работах. Для этого нужен ключ сервиса Claude компании Anthropic.
        </p>

        {settings.isPending && <Spinner />}
        {settings.error && <ErrorBox error={settings.error} onRetry={settings.refetch} />}
        {s && (
          <div className={`callout ${s.configured ? 'callout--ok' : 'callout--warn'}`}>
            {s.configured ? (
              <>
                <b>Подключено.</b> Ключ {s.key_hint}
                {s.source === 'env' ? ' задан в файле настроек сервера' : ' сохранён в панели'} · модель {s.model}
              </>
            ) : (
              <>
                <b>Не подключено.</b> Чат-помощник недоступен, отчёты проверяются только правилами.
              </>
            )}
          </div>
        )}

        <form className="form settings__form" onSubmit={submit}>
          <Field label={s?.configured ? 'Заменить ключ' : 'Ключ Claude API'} hint="Начинается с sk-ant-. Ключ проверяется перед сохранением.">
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="sk-ant-api03-…"
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
          <div className="settings__actions">
            <button type="submit" className="btn btn--primary" disabled={!key.trim() || save.isPending}>
              {save.isPending ? 'Проверяю…' : 'Проверить и сохранить'}
            </button>
            {s?.source === 'panel' && (
              <button
                type="button"
                className="btn btn--ghost"
                disabled={remove.isPending}
                onClick={() => confirm('Удалить ключ? Помощник перестанет работать.') && remove.mutate()}
              >
                Удалить ключ
              </button>
            )}
          </div>
        </form>

        <details className="settings__help">
          <summary>Где взять ключ?</summary>
          <ol>
            <li>
              Откройте <b>console.anthropic.com</b> и войдите (или зарегистрируйте организацию).
            </li>
            <li>Пополните баланс в разделе Billing.</li>
            <li>
              Раздел <b>API Keys</b> → <b>Create Key</b> → скопируйте ключ и вставьте сюда.
            </li>
          </ol>
          <p className="muted small">
            Ключ хранится на сервере и не показывается целиком. Помощник только читает данные и не может ничего
            изменить в системе.
          </p>
        </details>
      </section>
    </div>
  )
}
