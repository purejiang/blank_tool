import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('updateStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.resetModules()
  })

  describe('initial state', () => {
    it('starts in idle status', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.status).toBe('idle')
    })

    it('has null for version fields', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.latestVersion).toBeNull()
      expect(store.releaseNotes).toBeNull()
      expect(store.currentVersion).toBe('')
    })

    it('has zero download progress', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.downloadPercent).toBe(0)
      expect(store.downloadSpeed).toBeNull()
    })

    it('has null error', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      expect(store.error).toBeNull()
    })
  })

  describe('setStatus', () => {
    it('transitions status', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setStatus('checking')
      expect(store.status).toBe('checking')
      store.setStatus('downloading')
      expect(store.status).toBe('downloading')
      store.setStatus('downloaded')
      expect(store.status).toBe('downloaded')
      store.setStatus('error')
      expect(store.status).toBe('error')
    })
  })

  describe('setUpdateInfo', () => {
    it('sets version and release notes', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setUpdateInfo({
        version: '2.0.6',
        releaseNotes: '## Bug fixes\n- Fixed crash',
        releaseDate: '2026-06-20',
      })
      expect(store.latestVersion).toBe('2.0.6')
      expect(store.releaseNotes).toBe('## Bug fixes\n- Fixed crash')
    })
  })

  describe('setDownloadProgress', () => {
    it('updates progress values', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setDownloadProgress({ percent: 54.2, bytesPerSecond: 12800000, transferred: 67108864, total: 134217728 })
      expect(store.downloadPercent).toBe(54.2)
      expect(store.downloadSpeed).toBe(12800000)
    })
  })

  describe('reset', () => {
    it('resets all state to initial', async () => {
      const { useUpdateStore } = await import('@/renderer/stores/updateStore')
      const store = useUpdateStore()
      store.setStatus('downloading')
      store.setUpdateInfo({ version: '2.0.6', releaseNotes: 'test' })
      store.setDownloadProgress({ percent: 50, bytesPerSecond: 1000, transferred: 500, total: 1000 })
      store.reset()
      expect(store.status).toBe('idle')
      expect(store.latestVersion).toBeNull()
      expect(store.downloadPercent).toBe(0)
      expect(store.downloadSpeed).toBeNull()
    })
  })
})
