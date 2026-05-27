/**
 * Global test setup for vitest + happy-dom.
 * Provides localStorage and sessionStorage stubs that are missing in happy-dom.
 */

const store: Record<string, string> = {}

globalThis.localStorage = {
  getItem: (key: string): string | null => {
    return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null
  },
  setItem: (key: string, value: string): void => {
    store[key] = String(value)
  },
  removeItem: (key: string): void => {
    delete store[key]
  },
  clear: (): void => {
    Object.keys(store).forEach((k) => delete store[k])
  },
  get length(): number {
    return Object.keys(store).length
  },
  key: (index: number): string | null => {
    const keys = Object.keys(store)
    return keys[index] ?? null
  },
} as Storage

globalThis.sessionStorage = {
  getItem: (key: string): string | null => null,
  setItem: (_key: string, _value: string): void => {},
  removeItem: (_key: string): void => {},
  clear: (): void => {},
  get length(): number { return 0 },
  key: (_index: number): string | null => null,
} as Storage
