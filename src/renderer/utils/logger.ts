const isDev = import.meta.env.DEV
const isProd = !isDev

let currentLevel: 'debug' | 'info' | 'warn' | 'error' = 'info'

export function setLogLevel(level: 'debug' | 'info' | 'warn' | 'error'): void {
  currentLevel = level
}

// -- Ring buffer hook (set by useAppBootstrap after Pinia is ready) ----------
let _pushToRing: ((level: string, message: string) => void) | null = null

/**
 * Set the ring-buffer pusher. Called once during app bootstrap after
 * ``useRendererLogStore`` is initialised. The indirection avoids a
 * circular import (logger → store → logger).
 */
export function _setRingPusher(pusher: typeof _pushToRing): void {
  _pushToRing = pusher
}

function stringify(args: unknown[]): string {
  return args.map(a => a === undefined ? 'undefined' : a === null ? 'null' : String(a)).join(' ')
}

function record(level: 'debug' | 'info' | 'warn' | 'error', args: unknown[]): void {
  try {
    _pushToRing?.(level, stringify(args))
  } catch {
    // fire-and-forget: never let logging break the app
  }
}

function forward(level: 'error' | 'warn' | 'info', message: string): void {
  try {
    const api = window.electronAPI
    if (api && typeof api.rendererLog === 'function') {
      api.rendererLog(level, message)
    }
  } catch {
    // fire-and-forget: never let logging break the app
  }
}

export const log = {
  debug(...args: unknown[]): void {
    record('debug', args)
    if (isDev || currentLevel === 'debug') console.debug(...args)
  },
  error(...args: unknown[]): void {
    record('error', args)
    console.error(...args)
    if (isProd) forward('error', stringify(args))
  },
  warn(...args: unknown[]): void {
    record('warn', args)
    console.warn(...args)
    if (isProd) forward('warn', stringify(args))
  },
  info(...args: unknown[]): void {
    record('info', args)
    if (isDev || currentLevel === 'debug' || currentLevel === 'info') console.info(...args)
    if (isProd && (currentLevel === 'debug' || currentLevel === 'info')) forward('info', stringify(args))
  },
}
