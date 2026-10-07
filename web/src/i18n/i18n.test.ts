/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'

import ts from 'typescript'
import { afterEach, describe, expect, it } from 'vitest'

import { KK } from './kk'
import { localized, storeLang, t, tRich } from './lang'

const SRC = join(process.cwd(), 'src') // vitest запускается из web/
const CYR = /[А-Яа-яЁё]/
// Строки, которые не переводятся: префикс номера наряда, название продукта
const KEEP = new Set(['НР-', 'НарядAI', 'Н', 'Тіл / Язык'])

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
    const p = join(dir, d.name)
    if (d.isDirectory()) return sources(p)
    return /\.tsx?$/.test(d.name) && !/\.test\./.test(d.name) && !p.includes(join('i18n', 'kk.ts')) ? [p] : []
  })
}

/** Все русские тексты в коде панели: строковые литералы, текст в JSX, шаблонные строки. */
function scan() {
  const literals = new Map<string, string>() // текст → где встретился
  const problems: string[] = []
  for (const file of sources(SRC)) {
    const sf = ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const where = (n: ts.Node) => `${relative(SRC, file)}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`
    const visit = (node: ts.Node): void => {
      if (ts.isImportDeclaration(node)) return
      if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && CYR.test(node.text)) {
        if (!KEEP.has(node.text)) literals.set(node.text, where(node))
      } else if (ts.isJsxText(node) && CYR.test(node.text) && !KEEP.has(node.text.trim())) {
        problems.push(`${where(node)} русский текст прямо в разметке: «${node.text.trim()}» — оберните в t()`)
      } else if (
        ts.isTemplateExpression(node) &&
        CYR.test([node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join(''))
      ) {
        problems.push(`${where(node)} русский текст в шаблонной строке — используйте t('… {x}', { x })`)
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
  }
  return { literals, problems }
}

describe('перевод интерфейса на казахский', () => {
  const { literals, problems } = scan()

  it('нет русского текста мимо t()', () => {
    expect(problems).toEqual([])
  })

  it('у каждой русской строки есть казахский перевод', () => {
    const missing = [...literals].filter(([text]) => !(text in KK)).map(([text, at]) => `${at}  ${text}`)
    expect(missing).toEqual([])
  })

  it('в словаре нет переводов, которые больше нигде не используются', () => {
    const unused = Object.keys(KK).filter((ru) => !literals.has(ru))
    expect(unused).toEqual([])
  })

  it('подстановки {x} в переводе те же, что в оригинале', () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
    const broken = Object.entries(KK).filter(([ru, kk]) => names(ru).join() !== names(kk).join())
    expect(broken).toEqual([])
  })
})

describe('t()', () => {
  afterEach(() => storeLang('ru'))

  it('по-русски возвращает ключ, по-казахски — перевод, с подстановками', () => {
    expect(t('Выйти')).toBe('Выйти')
    storeLang('kk')
    expect(t('Выйти')).toBe(KK['Выйти'])
    expect(t('Нет такого ключа')).toBe('Нет такого ключа')
    expect(t('Сброс пароля: {fio}', { fio: 'Иванов' })).toContain('Иванов')
  })

  it('словари подписей читаются на текущем языке', () => {
    const STATUS = localized({ issued: 'Выдан' })
    expect(STATUS.issued).toBe('Выдан')
    storeLang('kk')
    expect(STATUS.issued).toBe(KK['Выдан'])
  })

  it('tRich ставит элементы на место {name}', () => {
    const parts = tRich('Откройте {site} и войдите (или зарегистрируйте организацию).', { site: 'X' })
    expect(parts).toHaveLength(3)
  })
})
