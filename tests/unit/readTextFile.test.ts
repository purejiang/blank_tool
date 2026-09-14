import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { readTextFile } from '@utils/readTextFile'

/**
 * readTextFile unit tests.
 *
 * The bridge returns the RAW main-process envelope `{ success, data }` —
 * everything that wants file *contents* must unwrap it. Regression guard for
 * the plugin page rendering the literal text "[object Object]" in its custom
 * UI iframe (the old code did `String(await readFile(...))`).
 */

const withApi = (readFile: unknown) => {
  ;(window as any).electronAPI = typeof readFile === 'function' ? { readFile } : readFile
}

describe('readTextFile', () => {
  beforeEach(() => { delete (window as any).electronAPI })
  afterEach(() => { delete (window as any).electronAPI })

  it('unwraps the { success, data } envelope', async () => {
    withApi(vi.fn(async () => ({ success: true, data: '<h1>hi</h1>' })))
    await expect(readTextFile('X:/a.html')).resolves.toBe('<h1>hi</h1>')
  })

  it('throws with the backend error message on success:false', async () => {
    withApi(vi.fn(async () => ({ success: false, error: 'ENOENT: no such file' })))
    await expect(readTextFile('X:/missing.html')).rejects.toThrow('ENOENT')
  })

  it('tolerates a plain string result (flattened bridge)', async () => {
    withApi(vi.fn(async () => 'raw text'))
    await expect(readTextFile('X:/a.txt')).resolves.toBe('raw text')
  })

  it('rejects a non-text payload instead of stringifying it', async () => {
    withApi(vi.fn(async () => ({ success: true, data: { nested: true } })))
    await expect(readTextFile('X:/a.bin')).rejects.toThrow(/did not return text/)
  })

  it('rejects when the bridge is unavailable', async () => {
    withApi(undefined)
    await expect(readTextFile('X:/a.txt')).rejects.toThrow(/unavailable/)
  })

  it('passes the path straight through', async () => {
    const fn = vi.fn(async () => ({ success: true, data: '' }))
    withApi(fn)
    await readTextFile('X:/plugins/p/ui/index.html')
    expect(fn).toHaveBeenCalledWith('X:/plugins/p/ui/index.html')
  })
})
