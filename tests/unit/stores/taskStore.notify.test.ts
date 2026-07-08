import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore, type Task } from '@/renderer/stores/taskStore'

function makeTask(store: ReturnType<typeof useTaskStore>, overrides: Partial<Task>): Task {
  const task = store.createTask({
    source: 'local',
    filePath: '/tmp/app.apk',
    fileName: 'app.apk',
    operation: 'decompile',
    operationLabel: 'Decompile',
  })
  Object.assign(task, overrides)
  return task
}

// appConfig.get is shared by auto-delete (autoDeleteOutputOnTaskRemove) and
// notifications (enableNotifications). Toggle only the notification key so the
// two features are controlled independently.
function setNotifyEnabled(enabled: boolean) {
  ;(window as any).electronAPI.appConfig.get = vi.fn((key: string) =>
    Promise.resolve(key === 'enableNotifications' ? enabled : false)
  )
}

describe('taskStore terminal-state notification', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    ;(globalThis as any).window = globalThis as any
    ;(window as any).electronAPI = {
      appConfig: { get: vi.fn((key: string) => Promise.resolve(false)) },
      callBackendAPI: vi.fn().mockResolvedValue({ deleted: [], failed: [] }),
      showSystemNotification: vi.fn().mockResolvedValue(true),
    }
  })

  it('1. toggle ON: fires notification once with title/body on terminal transition', async () => {
    setNotifyEnabled(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running' })

    store.updateTask(task.id, { status: 'completed' })

    await vi.waitFor(() => {
      expect((window as any).electronAPI.showSystemNotification).toHaveBeenCalledTimes(1)
    })
    const [title, body] = (window as any).electronAPI.showSystemNotification.mock.calls[0]
    expect(title).toContain('Decompile')
    expect(title).toContain('app.apk')
    expect(body).toBe('已完成')
  })

  it('2. toggle OFF: does not fire on terminal transition', async () => {
    setNotifyEnabled(false)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running' })

    store.updateTask(task.id, { status: 'failed' })
    await Promise.resolve()
    await Promise.resolve()

    expect((window as any).electronAPI.showSystemNotification).not.toHaveBeenCalled()
  })

  it('3. non-terminal transition: does not fire regardless of toggle', async () => {
    setNotifyEnabled(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'queued' })

    store.updateTask(task.id, { status: 'running' })
    await Promise.resolve()
    await Promise.resolve()

    expect((window as any).electronAPI.showSystemNotification).not.toHaveBeenCalled()
  })

  it('4. showSystemNotification rejects: no throw escapes updateTask, task still updated', async () => {
    setNotifyEnabled(true)
    ;(window as any).electronAPI.showSystemNotification = vi.fn().mockRejectedValue(new Error('boom'))
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running' })

    expect(() => store.updateTask(task.id, { status: 'cancelled' })).not.toThrow()
    // update is synchronous
    expect(store.tasks.find(t => t.id === task.id)?.status).toBe('cancelled')

    await vi.waitFor(() => {
      expect((window as any).electronAPI.showSystemNotification).toHaveBeenCalledTimes(1)
    })
    expect(store.tasks.find(t => t.id === task.id)?.status).toBe('cancelled')
    errSpy.mockRestore()
  })

  it('5. failed with error: body includes error detail', async () => {
    setNotifyEnabled(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running' })

    store.updateTask(task.id, { status: 'failed', error: 'oops' })

    await vi.waitFor(() => {
      expect((window as any).electronAPI.showSystemNotification).toHaveBeenCalledTimes(1)
    })
    const [, body] = (window as any).electronAPI.showSystemNotification.mock.calls[0]
    expect(body).toBe('失败: oops')
  })
})
