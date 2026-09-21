import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { promises as fs } from 'fs'
import path from 'path'

// ---------------------------------------------------------------------------
// electron / electron-log stubs — capture ipcMain.handle registrations
// ---------------------------------------------------------------------------

const registeredHandlers = new Map<string, Function>()
const mockShowSaveDialog = vi.fn()
const stubWindow = { id: 1 }
const mockFromWebContents = vi.fn(() => stubWindow as any)

vi.mock('electron', () => ({
  ipcMain: {
    handle: vi.fn((channel: string, handler: Function) => {
      registeredHandlers.set(channel, handler)
    }),
  },
  dialog: {
    showSaveDialog: (...args: any[]) => mockShowSaveDialog(...args),
    showOpenDialog: vi.fn(),
  },
  shell: { openPath: vi.fn(), showItemInFolder: vi.fn() },
  Tray: class {},
  BrowserWindow: { fromWebContents: (...args: any[]) => mockFromWebContents(...args) },
  app: {
    getVersion: () => '0.0.0-test',
    getName: () => 'blank_tool-test',
    getAppPath: () => process.cwd(),
    getPath: () => process.cwd(),
    isPackaged: false,
  },
  clipboard: { writeText: vi.fn() },
  Notification: class {
    static isSupported() {
      return false
    }
    on() {}
    show() {}
  },
}))

vi.mock('electron-log', () => {
  const noop = { error: vi.fn(), warn: vi.fn(), info: vi.fn(), log: vi.fn(), debug: vi.fn() }
  return { default: noop, ...noop }
})

// ---------------------------------------------------------------------------
// Real fs, scratch dir inside the repo (.tmp is gitignored — os.tmpdir() is
// blocked in this sandbox).
// ---------------------------------------------------------------------------

const scratchDir = path.join(process.cwd(), '.tmp', 'filechannels-test')

let invoke: (channel: string, payload?: any) => Promise<any>

beforeEach(async () => {
  registeredHandlers.clear()
  mockShowSaveDialog.mockReset()
  mockFromWebContents.mockReturnValue(stubWindow as any)

  const { setupElectronHandlers } = await import('@/main/ipc/electronHandlers')
  setupElectronHandlers()

  invoke = (channel: string, payload?: any) => {
    const handler = registeredHandlers.get(channel)
    if (!handler) throw new Error(`handler not registered: ${channel}`)
    return handler({ sender: {} }, payload)
  }

  await fs.rm(scratchDir, { recursive: true, force: true })
})

afterEach(async () => {
  await fs.rm(scratchDir, { recursive: true, force: true })
})

describe('write-text-file / read-text-file', () => {
  it('writes then reads back the same content (round-trip)', async () => {
    const p = path.join(scratchDir, 'roundtrip.json')

    const written = await invoke('write-text-file', { path: p, content: '{"a":1,"b":"中文"}' })
    expect(written).toEqual({ success: true })

    const read = await invoke('read-text-file', { path: p })
    expect(read).toEqual({ success: true, content: '{"a":1,"b":"中文"}' })
  })

  it('auto-creates the parent directory', async () => {
    const p = path.join(scratchDir, 'deep', 'nested', 'a.txt')

    const written = await invoke('write-text-file', { path: p, content: 'hello' })
    expect(written.success).toBe(true)

    const stat = await fs.stat(p)
    expect(stat.isFile()).toBe(true)
  })

  it('does not leave a .tmp file behind on success', async () => {
    const p = path.join(scratchDir, 'clean.txt')
    await invoke('write-text-file', { path: p, content: 'x' })

    await expect(fs.stat(`${p}.tmp`)).rejects.toBeTruthy()
  })

  it('rejects content over maxBytes with success:false and no content', async () => {
    const p = path.join(scratchDir, 'big.txt')
    await invoke('write-text-file', { path: p, content: '0123456789' })

    const read = await invoke('read-text-file', { path: p, maxBytes: 4 })
    expect(read.success).toBe(false)
    expect(read.error).toBe('file too large')
    expect(read.content).toBeUndefined()
  })

  it('reads content within the default 8 MiB budget without maxBytes', async () => {
    const p = path.join(scratchDir, 'default-budget.txt')
    await invoke('write-text-file', { path: p, content: 'small' })

    const read = await invoke('read-text-file', { path: p })
    expect(read).toEqual({ success: true, content: 'small' })
  })

  it('returns {success:false} (never throws) when the write parent path is a file', async () => {
    await fs.mkdir(scratchDir, { recursive: true })
    const blocker = path.join(scratchDir, 'blocker.txt')
    await fs.writeFile(blocker, 'i am a file', 'utf8')

    const result = await invoke('write-text-file', { path: path.join(blocker, 'child.txt'), content: 'x' })
    expect(result.success).toBe(false)
    expect(typeof result.error).toBe('string')
  })

  it('returns {success:false} (never throws) when reading a missing path', async () => {
    const result = await invoke('read-text-file', { path: path.join(scratchDir, 'does-not-exist.txt') })
    expect(result.success).toBe(false)
    expect(typeof result.error).toBe('string')
  })

  it('returns {success:false} when the path is empty', async () => {
    expect((await invoke('write-text-file', { path: '', content: 'x' })).success).toBe(false)
    expect((await invoke('read-text-file', { path: '' })).success).toBe(false)
  })
})

describe('show-save-dialog', () => {
  it('passes defaultPath / filters / title through and echoes the cancel', async () => {
    mockShowSaveDialog.mockResolvedValue({ canceled: true, filePath: undefined })
    const options = {
      defaultPath: 'workflow.json',
      filters: [{ name: 'JSON', extensions: ['json'] }],
      title: '导出工作流',
    }

    const result = await invoke('show-save-dialog', options)

    expect(result).toEqual({ canceled: true })
    expect(mockShowSaveDialog).toHaveBeenCalledTimes(1)
    const [win, dialogOptions] = mockShowSaveDialog.mock.calls[0]
    expect(win).toBe(stubWindow)
    expect(dialogOptions).toEqual(options)
  })

  it('returns the chosen filePath when the user confirms', async () => {
    mockShowSaveDialog.mockResolvedValue({ canceled: false, filePath: 'C:\\out\\wf.json' })

    const result = await invoke('show-save-dialog', { defaultPath: 'wf.json' })

    expect(result).toEqual({ canceled: false, filePath: 'C:\\out\\wf.json' })
  })

  it('returns {canceled:true} without opening a dialog when there is no window', async () => {
    mockFromWebContents.mockReturnValueOnce(null as any)

    const result = await invoke('show-save-dialog', { defaultPath: 'wf.json' })

    expect(result).toEqual({ canceled: true })
    expect(mockShowSaveDialog).not.toHaveBeenCalled()
  })

  it('returns {canceled:true} instead of throwing when the dialog rejects', async () => {
    mockShowSaveDialog.mockRejectedValue(new Error('dialog boom'))

    const result = await invoke('show-save-dialog', {})

    expect(result).toEqual({ canceled: true })
  })
})
