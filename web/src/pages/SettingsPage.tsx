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

interface ConnectionInfo {
  lan_ips: string[]
  web_port: number
}

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])
/** Приложение само подставляет порт 8080 — тогда достаточно IP. */
const phoneAddress = (host: string, port: number) => (port === 8080 ? host : `${host}:${port}`)

/** Адреса, которые можно ввести в мобильном приложении: IP от скрипта запуска + адрес, по которому открыта панель. */
function phoneAddresses(info: ConnectionInfo | undefined): string[] {
  const list = (info?.lan_ips ?? []).map((ip) => phoneAddress(ip, info!.web_port))
  const { hostname, port, protocol } = window.location
  if (!LOCAL_HOSTS.has(hostname)) {
    list.push(phoneAddress(hostname, Number(port) || (protocol === 'https:' ? 443 : 80)))
  }
  return [...new Set(list)]
}

/** navigator.clipboard работает только на https и localhost — на http по IP копируем через выделение. */
async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    area.remove()
  }
}

/** Какой адрес ввести в мобильном приложении («Сервер → Изменить» на экране входа). */
function PhoneConnection() {
  const toast = useToast()
  const info = useQuery({
    queryKey: ['settings', 'connection'],
    queryFn: () => api<ConnectionInfo>('/settings/connection'),
  })
  const addresses = phoneAddresses(info.data)

  return (
    <section className="panel">
      <h2>{t('📱 Подключение мобильного приложения')}</h2>
      <p className="muted">
        {t('Исполнители работают в приложении на телефоне. Телефон должен быть в той же Wi-Fi сети, что и этот компьютер.')}
      </p>

      {info.isPending && <Spinner />}
      {info.error && <ErrorBox error={info.error} onRetry={info.refetch} />}
      {info.isSuccess &&
        (addresses.length > 0 ? (
          <div className="connect__list">
            {addresses.map((addr) => (
              <div key={addr} className="connect__addr">
                <span className="mono">{addr}</span>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => copyText(addr).then(() => toast.success(t('Адрес скопирован')))}
                >
                  {t('Копировать')}
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="callout callout--warn">
            {t('IP этого компьютера неизвестен: запустите систему через start.bat (Windows) или start.sh (Linux, macOS) или узнайте IP командой ipconfig.')}
          </div>
        ))}

      <ol className="connect__steps">
        <li>{tRich('В приложении на экране входа нажмите {change} в строке «Сервер».', { change: <b>{t('Изменить')}</b> })}</li>
        <li>{t('Введите адрес выше в поле «Адрес сервера».')}</li>
        <li>{tRich('Нажмите {save} и войдите.', { save: <b>{t('Проверить и сохранить')}</b> })}</li>
      </ol>
      <p className="muted small">
        {t('Android-эмулятор на этом компьютере подключается сам — вводить ничего не нужно. Сменилась Wi-Fi сеть — перезапустите start.bat, адрес обновится.')}
      </p>
    </section>
  )
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

      <PhoneConnection />

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
