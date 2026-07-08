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

describe('taskStore auto-delete output', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    ;(globalThis as any).window = globalThis as any
    ;(window as any).electronAPI = {
      appConfig: { get: vi.fn() },
      callBackendAPI: vi.fn().mockResolvedValue({ deleted: [], failed: [] }),
    }
  })

  it('1. toggle OFF: does not call backend when removing a completed task', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(false)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'completed', outputPath: '/out/x' })

    store.removeTask(task.id)
    await Promise.resolve()
    await Promise.resolve()

    expect((window as any).electronAPI.callBackendAPI).not.toHaveBeenCalled()
    expect(store.tasks.find(t => t.id === task.id)).toBeUndefined()
  })

  it('2. toggle ON: calls backend once with the terminal task outputPath', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'completed', outputPath: 'X' })

    store.removeTask(task.id)
    await vi.waitFor(() => {
      expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledTimes(1)
    })
    expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledWith('task.delete_output', { paths: ['X'] })
  })

  it('3. toggle ON: running task excluded, backend not called', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running', outputPath: '/out/running' })

    store.removeTask(task.id)
    await Promise.resolve()
    await Promise.resolve()

    expect((window as any).electronAPI.callBackendAPI).not.toHaveBeenCalled()
    expect(store.tasks.find(t => t.id === task.id)).toBeUndefined()
  })

  it('4. toggle ON: empty outputPath is not included', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'completed', outputPath: '' })

    store.removeTask(task.id)
    await Promise.resolve()
    await Promise.resolve()

    expect((window as any).electronAPI.callBackendAPI).not.toHaveBeenCalled()
  })

  it('5. toggle ON: backend rejects but record is still removed (no throw escapes)', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(true)
    ;(window as any).electronAPI.callBackendAPI = vi.fn().mockRejectedValue(new Error('boom'))
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const store = useTaskStore()
    const task = makeTask(store, { status: 'completed', outputPath: '/out/y' })

    store.removeTask(task.id)
    // record removal is synchronous / immediate
    expect(store.tasks.find(t => t.id === task.id)).toBeUndefined()

    await vi.waitFor(() => {
      expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledTimes(1)
    })
    // still not present, and the rejection was swallowed
    expect(store.tasks.find(t => t.id === task.id)).toBeUndefined()
    errSpy.mockRestore()
  })
})
