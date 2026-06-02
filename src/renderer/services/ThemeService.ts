import { darkTheme } from 'naive-ui'
import type { GlobalTheme } from 'naive-ui'

type ThemeMode = 'auto' | 'light' | 'dark'
type ThemeChangeCallback = (theme: GlobalTheme | null) => void

export class ThemeService {
  private mode: ThemeMode
  private systemDark: boolean
  private mediaQuery: MediaQueryList | null
  private listeners: Set<ThemeChangeCallback>

  constructor() {
    this.mode = 'auto'
    this.systemDark = false
    this.mediaQuery = null
    this.listeners = new Set()
  }

  async initialize() {
    if (typeof window !== 'undefined' && window.matchMedia) {
      this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      this.systemDark = this.mediaQuery.matches
      this.mediaQuery.addEventListener('change', (e) => {
        this.systemDark = e.matches
        if (this.mode === 'auto') {
          this.notifyListeners()
        }
      })
    }
  }

  async applyTheme(): Promise<GlobalTheme | null> {
    const actual = this.resolveActual()
    const theme = actual === 'dark' ? darkTheme : null
    document.documentElement.setAttribute('data-theme', actual)
    this.notifyListeners()
    return theme
  }

  async setTheme(mode: ThemeMode): Promise<GlobalTheme | null> {
    this.mode = mode
    return this.applyTheme()
  }

  getCurrentTheme(): ThemeMode {
    return this.mode
  }

  getActualTheme(): 'light' | 'dark' {
    return this.resolveActual()
  }

  onChange(callback: ThemeChangeCallback): () => void {
    this.listeners.add(callback)
    return () => this.listeners.delete(callback)
  }

  private resolveActual(): 'light' | 'dark' {
    if (this.mode === 'auto') {
      return this.systemDark ? 'dark' : 'light'
    }
    return this.mode
  }

  private notifyListeners() {
    const theme = this.resolveActual() === 'dark' ? darkTheme : null
    this.listeners.forEach(cb => cb(theme))
  }

  destroy() {
    if (this.mediaQuery) {
      this.mediaQuery.removeEventListener('change', () => {})
      this.mediaQuery = null
    }
    this.listeners.clear()
  }
}
