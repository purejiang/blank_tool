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

describe('taskStore auto-delete task dir', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    ;(globalThis as any).window = globalThis as any
    ;(window as any).electronAPI = {
      appConfig: { get: vi.fn() },
      callBackendAPI: vi.fn().mockResolvedValue({ deleted: true, path: '' }),
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

  it('2. toggle ON: calls backend once with task.delete_task_dir and task_id', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'completed', outputPath: 'X' })

    store.removeTask(task.id)
    await vi.waitFor(() => {
      expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledTimes(1)
    })
    expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledWith('task.delete_task_dir', { task_id: String(task.id) })
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

  it('4. toggle ON: completed task with empty outputPath still triggers delete (id-based)', async () => {
    ;(window as any).electronAPI.appConfig.get.mockResolvedValue(true)
    const store = useTaskStore()
    const task = makeTask(store, { status: 'completed', outputPath: '' })

    store.removeTask(task.id)
    await vi.waitFor(() => {
      expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledTimes(1)
    })
    expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledWith('task.delete_task_dir', { task_id: String(task.id) })
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

  it('6. appendLog persists line via task.append_log', async () => {
    ;(window as any).electronAPI.callBackendAPI = vi.fn().mockResolvedValue({ written: true })
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running' })

    store.appendLog(task.id, 'line one')

    // In-memory append is synchronous
    expect(task.logs).toContain('line one')

    // Persistence is fire-and-forget; wait for the async call
    await vi.waitFor(() => {
      expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledWith(
        'task.append_log',
        { task_id: String(task.id), line: 'line one' },
      )
    })
  })

  it('7. appendLog does not throw when backend call fails', async () => {
    ;(window as any).electronAPI.callBackendAPI = vi.fn().mockRejectedValue(new Error('boom'))
    const store = useTaskStore()
    const task = makeTask(store, { status: 'running' })

    // Must not throw
    expect(() => store.appendLog(task.id, 'line two')).not.toThrow()

    // In-memory append still works
    expect(task.logs).toContain('line two')

    await vi.waitFor(() => {
      expect((window as any).electronAPI.callBackendAPI).toHaveBeenCalledWith(
        'task.append_log',
        { task_id: String(task.id), line: 'line two' },
      )
    })
  })
})
