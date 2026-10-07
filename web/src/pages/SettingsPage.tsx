import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import { useToast } from '../components/useToast'
import { ErrorBox, Field, Spinner } from '../components/ui'
import { t, tRich } from '../i18n/lang'

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
      toast.success(t('Ключ проверен и сохранён — помощник готов'))
    },
    onError: toast.error,
  })
  const remove = useMutation({
    mutationFn: () => api<void>('/settings/assistant', { method: 'DELETE' }),
    onSuccess: () => {
      done()
      toast.success(t('Ключ удалён'))
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
        <h1>{t('Настройки')}</h1>
      </div>

      <section className="panel">
        <h2>{t('✦ ИИ-помощник и ИИ-проверка нарядов')}</h2>
        <p className="muted">
          {t('Помощник отвечает на вопросы в чате (кнопка «Помощник» внизу справа), а ИИ дополнительно проверяет смысл отчётов о выполненных работах. Работает на Google Gemini — ключ бесплатный.')}
        </p>

        {settings.isPending && <Spinner />}
        {settings.error && <ErrorBox error={settings.error} onRetry={settings.refetch} />}
        {s && (
          <div className={`callout ${s.configured ? 'callout--ok' : 'callout--warn'}`}>
            {s.configured ? (
              <>
                <b>{t('Подключено.')}</b>{' '}
                {s.source === 'env'
                  ? t('Ключ {key} задан в файле настроек сервера', { key: s.key_hint ?? '' })
                  : t('Ключ {key} сохранён в панели', { key: s.key_hint ?? '' })}{' '}
                · {t('модель')} {s.model}
              </>
            ) : (
              <>
                <b>{t('Не подключено.')}</b> {t('Чат-помощник недоступен, отчёты проверяются только правилами.')}
              </>
            )}
          </div>
        )}

        <form className="form settings__form" onSubmit={submit}>
          <Field label={s?.configured ? t('Заменить ключ') : t('Ключ Gemini API')} hint={t('Начинается с AIza. Ключ проверяется перед сохранением.')}>
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="AIzaSy…"
              autoComplete="off"
              spellCheck={false}
            />
          </Field>
          <div className="settings__actions">
            <button type="submit" className="btn btn--primary" disabled={!key.trim() || save.isPending}>
              {save.isPending ? t('Проверяю…') : t('Проверить и сохранить')}
            </button>
            {s?.source === 'panel' && (
              <button
                type="button"
                className="btn btn--ghost"
                disabled={remove.isPending}
                onClick={() => confirm(t('Удалить ключ? Помощник перестанет работать.')) && remove.mutate()}
              >
                {t('Удалить ключ')}
              </button>
            )}
          </div>
        </form>

        <details className="settings__help">
          <summary>{t('Где взять ключ?')}</summary>
          <ol>
            <li>
              {tRich('Откройте {site} и войдите под аккаунтом Google.', { site: <b>aistudio.google.com</b> })}
            </li>
            <li>
              {tRich('Нажмите {get} → {create} — оплата и карта не нужны.', {
                get: <b>Get API key</b>,
                create: <b>Create API key</b>,
              })}
            </li>
            <li>{t('Скопируйте ключ (начинается с AIza) и вставьте сюда.')}</li>
          </ol>
          <p className="muted small">
            {t('Бесплатный тариф ограничен числом запросов в минуту и в сутки — при превышении помощник попросит подождать. На бесплатном тарифе Google может использовать запросы для улучшения своих сервисов; если это недопустимо, включите оплату для проекта ключа в AI Studio.')}
          </p>
          <p className="muted small">
            {t('Ключ хранится на сервере и не показывается целиком. Помощник только читает данные и не может ничего изменить в системе.')}
          </p>
        </details>
      </section>
    </div>
  )
}
