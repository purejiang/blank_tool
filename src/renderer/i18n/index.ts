import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

function detectLocale(): string {
  // Check navigator language for browser-like environment
  const nav = (typeof navigator !== 'undefined' && navigator.language) || ''
  if (nav.startsWith('zh')) return 'zh-CN'
  if (nav.startsWith('en')) return 'en-US'
  return 'zh-CN'
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
