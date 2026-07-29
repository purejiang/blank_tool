import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface RendererLogEntry {
  ts: number
  level: 'debug' | 'info' | 'warn' | 'error'
  message: string
}

const RING_MAX = 500

/**
 * In-memory ring buffer for renderer-side log entries.
 *
 * NOT persisted — memory-only. Entries are pushed by logger.ts
 * via a setter callback wired during app bootstrap. T29 (Diagnostics
 * panel) consumes ``getTail()``.
 */
export const useRendererLogStore = defineStore('rendererLog', () => {
  const entries = ref<RendererLogEntry[]>([])

  function push(level: RendererLogEntry['level'], message: string): void {
    entries.value.push({ ts: Date.now(), level, message })
    if (entries.value.length > RING_MAX) {
      entries.value.splice(0, entries.value.length - RING_MAX)
    }
  }

  function getTail(lines: number = 200): RendererLogEntry[] {
    const n = Math.max(1, Math.min(lines, RING_MAX))
    return entries.value.slice(-n)
  }

  function clear(): void {
    entries.value = []
  }

  return { entries, push, getTail, clear }
}, { persist: false })
