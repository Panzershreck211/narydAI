import { useQueryClient } from '@tanstack/react-query'
import { Fragment, type ReactNode, useCallback, useMemo, useState } from 'react'

import { getLang, type Lang, LangContext, storeLang } from './lang'

/** Смена языка перемонтирует интерфейс и перезапрашивает данные — сервер отдаёт свои тексты на новом языке. */
export function LangProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [lang, setState] = useState<Lang>(getLang)
  const setLang = useCallback(
    (next: Lang) => {
      storeLang(next)
      setState(next)
      void queryClient.invalidateQueries()
    },
    [queryClient],
  )
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang])
  return (
    <LangContext value={value}>
      <Fragment key={lang}>{children}</Fragment>
    </LangContext>
  )
}
