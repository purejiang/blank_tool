import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * CacheService envelope handling.
 *
 * `callBackendAPI` RESOLVES to a failure envelope (`{success:false, error}`)
 * instead of throwing — a backend that is still starting up produces one. Before
 * the guard, `getCacheInfo` assigned that straight into its cache, SettingsPage
 * read `.total.size` off undefined on the next render and the storage card blew
 * up (the red toast in the settings screenshots).
 */

const getCacheInfo = vi.fn()

// Must exist BEFORE the service module is imported: unifiedApi's singleton runs
// initialize() at import time and binds to whatever window.electronAPI is then.
Object.defineProperty(globalThis, 'window', {
  value: { electronAPI: { getCacheInfo, callBackendAPI: vi.fn() } },
  writable: true,
})

import unifiedApi from '@/renderer/api/unifiedApi'
import CacheService from '@/renderer/services/CacheService'

const EMPTY = { tasks: { size: 0, files: 0 }, output: { size: 0, files: 0 }, logs: { size: 0, files: 0 }, total: { size: 0, files: 0 } }

function info(totalSize: number) {
  return {
    tasks: { size: 1, files: 1 },
    output: { size: 2, files: 1 },
    logs: { size: 3, files: 1 },
    total: { size: totalSize, files: 3 },
  }
}

describe('CacheService.getCacheInfo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Re-bind the singleton to the stubbed window (it was created at import time).
    unifiedApi.initialize()
  })

  it('returns the backend payload when it is shaped like CacheInfo', async () => {
    const payload = info(6)
    getCacheInfo.mockResolvedValue(payload)

    expect(await new CacheService().getCacheInfo(true)).toEqual(payload)
  })

  it('falls back to the empty shape for a {success:false} failure envelope', async () => {
    getCacheInfo.mockResolvedValue({ success: false, error: 'backend not ready' })

    expect(await new CacheService().getCacheInfo(true)).toEqual(EMPTY)
  })

  it('falls back when the payload has no usable total block', async () => {
    getCacheInfo.mockResolvedValue({ tasks: { size: 1, files: 1 } })

    expect(await new CacheService().getCacheInfo(true)).toEqual(EMPTY)
  })

  it('does not cache the fallback, so a later retry can still succeed', async () => {
    getCacheInfo.mockResolvedValueOnce({ success: false, error: 'x' })
    const service = new CacheService()
    await service.getCacheInfo(true)

    const payload = info(9)
    getCacheInfo.mockResolvedValue(payload)

    expect(await service.getCacheInfo()).toEqual(payload)
  })
})
