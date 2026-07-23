const isDev = import.meta.env.DEV
const isProd = !isDev

function stringify(args: unknown[]): string {
  return args.map(a => a === undefined ? 'undefined' : a === null ? 'null' : String(a)).join(' ')
}

function forward(level: 'error' | 'warn', message: string): void {
  try {
    const api = (window as any).electronAPI
    if (api && typeof api.rendererLog === 'function') {
      api.rendererLog(level, message)
    }
  } catch {
    // fire-and-forget: never let logging break the app
  }
}

export const log = {
  debug(...args: unknown[]): void {
    if (isDev) console.debug(...args)
    // silent in production — debug is dev-only by design
  },
  error(...args: unknown[]): void {
    console.error(...args)
    if (isProd) forward('error', stringify(args))
  },
  warn(...args: unknown[]): void {
    console.warn(...args)
    if (isProd) forward('warn', stringify(args))
  },
  info(...args: unknown[]): void {
    if (isDev) console.info(...args)
    // silent in production
  },
}
