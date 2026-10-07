import { useLang } from './lang'

/** Кнопка «Қаз / Рус»: подсвечен текущий язык. */
export function LangSwitch({ className = '' }: { className?: string }) {
  const { lang, setLang } = useLang()
  return (
    <div className={`langswitch ${className}`} role="group" aria-label="Тіл / Язык">
      {(['kk', 'ru'] as const).map((l) => (
        <button
          key={l}
          type="button"
          className={`langswitch__btn${lang === l ? ' is-active' : ''}`}
          aria-pressed={lang === l}
          onClick={() => setLang(l)}
        >
          {l === 'kk' ? 'Қаз' : 'Рус'}
        </button>
      ))}
    </div>
  )
}
