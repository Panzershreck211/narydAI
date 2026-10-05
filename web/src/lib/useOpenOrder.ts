import { useSearchParams } from 'react-router'

/** Открыть карточку наряда (боковая панель) — состояние в URL, ссылкой можно поделиться. */
export function useOpenOrder() {
  const [, setParams] = useSearchParams()
  return (id: number) =>
    setParams((p) => {
      p.set('order', String(id))
      return p
    })
}
