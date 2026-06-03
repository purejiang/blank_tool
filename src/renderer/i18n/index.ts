import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

const LANG_KEY = 'app-language'

function getStoredLang(): string | null {
  try {
    const stored = localStorage.getItem(LANG_KEY)
    if (stored && (stored === 'zh-CN' || stored === 'en-US')) return stored
  } catch {}
  return null
}

function detectLocale(): string {
  const stored = getStoredLang()
  if (stored) return stored
  const nav = (typeof navigator !== 'undefined' && navigator.language) || ''
  if (nav.startsWith('zh')) return 'zh-CN'
  if (nav.startsWith('en')) return 'en-US'
  return 'zh-CN'
}

export function persistLocale(lang: string) {
  try { localStorage.setItem(LANG_KEY, lang) } catch {}
}

const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export default i18n
