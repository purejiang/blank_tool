/**
 * Add-step dropdown coverage — every ADDABLE_ACTIONS entry must render a real
 * label. OtherToolsPage builds the menu from ADDABLE_ACTIONS and resolves each
 * label through `stepActionLabel` → `automation.act.<action>`; a missing `act`
 * key would ship the raw dotted key as the menu label.
 */
import { describe, it, expect } from 'vitest'
import { ADDABLE_ACTIONS } from '@components/automation/stepTypes'
import { stepActionLabel } from '@components/automation/stepMeta'
import zh from '@/renderer/i18n/locales/zh-CN'
import en from '@/renderer/i18n/locales/en-US'

/** Stand-in for vue-i18n `t` that walks the real locale tree (missing → key). */
function localeT(locale: object): (key: string) => string {
  return (key: string) => {
    let node: unknown = locale
    for (const part of key.split('.')) {
      if (node === null || typeof node !== 'object') return key
      node = (node as Record<string, unknown>)[part]
    }
    return typeof node === 'string' ? node : key
  }
}

describe('ADDABLE_ACTIONS — add-step dropdown entries', () => {
  it('offers assert_element alongside assert_activity', () => {
    expect(ADDABLE_ACTIONS).toContain('assert_element')
  })

  it('resolves a real label for every entry in both locales', () => {
    for (const action of ADDABLE_ACTIONS) {
      const key = `automation.act.${action}`
      expect(stepActionLabel(action, localeT(zh)), `zh-CN missing ${key}`).not.toBe(key)
      expect(stepActionLabel(action, localeT(en)), `en-US missing ${key}`).not.toBe(key)
    }
  })
})
