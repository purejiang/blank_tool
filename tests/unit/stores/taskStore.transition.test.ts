import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore, type Task } from '@/renderer/stores/taskStore'

function makeTask(store: ReturnType<typeof useTaskStore>, overrides?: Partial<Task>): Task {
  const task = store.createTask({
    source: 'local',
    filePath: '/tmp/app.apk',
    fileName: 'app.apk',
    operation: 'decompile',
    operationLabel: 'Decompile',
  })
  if (overrides) Object.assign(task, overrides)
  return task
}

function setNotifyEnabled(enabled: boolean) {
  ;(window as any).electronAPI.appConfig.get = vi.fn((key: string) =>
    Promise.resolve(key === 'enableNotifications' ? enabled : false)
  )
}

describe('taskStore transition state machine', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    ;(globalThis as any).window = globalThis as any
    ;(window as any).electronAPI = {
      appConfig: { get: vi.fn((key: string) => Promise.resolve(false)) },
      callBackendAPI: vi.fn().mockResolvedValue({}),
      showSystemNotification: vi.fn().mockResolvedValue(true),
    }
  })

  // ──── createTask phase initialization ────

  it('1. createTask with source=url initializes phase=download, status=downloading', () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'url',
      url: 'https://example.com/app.apk',
      filePath: '',
      fileName: 'app.apk',
      operation: 'install',
      operationLabel: 'Install',
    })
    expect(task.phase).toBe('download')
    expect(task.status).toBe('downloading')
  })

  it('2. createTask with source=local initializes phase=idle, status=queued', () => {
    const store = useTaskStore()
    const task = makeTask(store)
    expect(task.phase).toBe('idle')
    expect(task.status).toBe('queued')
  })

  // ──── transition events ────

  it('3. start_download sets phase=download, status=downloading, progress=0', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'idle', status: 'queued' })
    store.transition(task.id, 'start_download')
    expect(task.phase).toBe('download')
    expect(task.status).toBe('downloading')
    expect(task.progress).toBe(0)
  })

  it('4. download_complete updates filePath and progress=100 without changing phase', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'download', status: 'downloading', progress: 50 })
    store.transition(task.id, 'download_complete', { file_path: '/downloads/app.apk' })
    expect(task.filePath).toBe('/downloads/app.apk')
    expect(task.progress).toBe(100)
    expect(task.phase).toBe('download') // phase unchanged
  })

  it('5. operation_complete sets status=completed, phase=finished, finishedAt, outputPath', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running', progress: 45 })
    // Flat shape: PackagePage's onComplete extracts fields before calling transition
    store.transition(task.id, 'operation_complete', { output_dir: '/out/decompiled' })
    expect(task.status).toBe('completed')
    expect(task.phase).toBe('finished')
    expect(task.progress).toBe(100)
    expect(task.finishedAt).toBeGreaterThan(0)
    expect(task.outputPath).toBe('/out/decompiled')
    expect(task.result).toBe('')
  })

  it('6. operation_error sets status=failed, phase=finished, error, finishedAt', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running' })
    store.transition(task.id, 'operation_error', { message: 'disk full' })
    expect(task.status).toBe('failed')
    expect(task.phase).toBe('finished')
    expect(task.error).toBe('disk full')
    expect(task.finishedAt).toBeGreaterThan(0)
  })

  it('7. cancel_request sets status=cancelling without changing phase', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'download', status: 'downloading' })
    store.transition(task.id, 'cancel_request')
    expect(task.status).toBe('cancelling')
    expect(task.phase).toBe('download') // phase unchanged
  })

  it('8. cancel_ack sets status=cancelled, phase=finished, finishedAt', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'download', status: 'cancelling' })
    store.transition(task.id, 'cancel_ack')
    expect(task.status).toBe('cancelled')
    expect(task.phase).toBe('finished')
    expect(task.finishedAt).toBeGreaterThan(0)
  })

  it('9. reset_for_retry resets to queued/idle with cleared error/result/progress', () => {
    const store = useTaskStore()
    const task = makeTask(store, {
      status: 'failed',
      phase: 'finished',
      error: 'old error',
      result: 'old result',
      progress: 100,
      progressLabel: '100%',
      finishedAt: 1234567890,
    })
    const beforeStartedAt = task.startedAt

    store.transition(task.id, 'reset_for_retry')

    expect(task.status).toBe('queued')
    expect(task.phase).toBe('idle')
    expect(task.error).toBe('')
    expect(task.result).toBe('')
    expect(task.progress).toBe(0)
    expect(task.progressLabel).toBe('')
    expect(task.finishedAt).toBeNull()
    expect(task.startedAt).toBeGreaterThanOrEqual(beforeStartedAt)
  })

  // ──── backward compatibility ────

  it('10. loadTasks infers phase=finished for terminal statuses, idle otherwise', () => {
    // Pre-populate localStorage with pre-phase JSON (no phase field)
    const oldData = [
      {
        id: 1, source: 'local', filePath: '/a.apk', fileName: 'a.apk',
        operation: 'decompile', operationLabel: 'Decompile',
        status: 'completed', progress: 100, progressLabel: '100%',
        result: '', outputPath: '/out', logs: [], error: '',
        collapsed: false, createdAt: 1000, startedAt: 1000,
        finishedAt: 2000, taskDir: '',
      },
      {
        id: 2, source: 'url', url: 'https://x', filePath: '', fileName: 'b.apk',
        operation: 'install', operationLabel: 'Install',
        status: 'failed', progress: 0, progressLabel: '',
        result: '', outputPath: '', logs: [], error: 'boom',
        collapsed: false, createdAt: 2000, startedAt: 2000,
        finishedAt: 3000, taskDir: '',
      },
      {
        id: 3, source: 'local', filePath: '/c.apk', fileName: 'c.apk',
        operation: 'analyze', operationLabel: 'Analyze',
        status: 'cancelled', progress: 0, progressLabel: '',
        result: '', outputPath: '', logs: [], error: '',
        collapsed: false, createdAt: 3000, startedAt: 3000,
        finishedAt: 4000, taskDir: '',
      },
      {
        id: 4, source: 'local', filePath: '/d.apk', fileName: 'd.apk',
        operation: 'resign', operationLabel: 'Resign',
        status: 'running', progress: 50, progressLabel: '50%',
        result: '', outputPath: '', logs: [], error: '',
        collapsed: false, createdAt: 4000, startedAt: 4000,
        finishedAt: null, taskDir: '',
      },
    ]
    localStorage.setItem('task-history', JSON.stringify(oldData))

    // Create fresh store — loadTasks runs on definition
    const store2 = useTaskStore()
    const tasks = store2.tasks

    const t1 = tasks.find(t => t.id === 1)!
    const t2 = tasks.find(t => t.id === 2)!
    const t3 = tasks.find(t => t.id === 3)!
    const t4 = tasks.find(t => t.id === 4)!

    expect(t1.phase).toBe('finished')  // completed → finished
    expect(t2.phase).toBe('finished')  // failed → finished
    expect(t3.phase).toBe('finished')  // cancelled → finished
    expect(t4.phase).toBe('idle')      // running → idle
  })

  // ──── terminal notification ────

  it('11. terminal transition (operation_complete) triggers showSystemNotification', async () => {
    setNotifyEnabled(true)
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running' })

    store.transition(task.id, 'operation_complete', { output_dir: '/out/done' })

    // notification is fire-and-forget; wait for async
    await vi.waitFor(() => {
      expect((window as any).electronAPI.showSystemNotification).toHaveBeenCalledTimes(1)
    })
    const [title, body] = (window as any).electronAPI.showSystemNotification.mock.calls[0]
    expect(title).toContain('Decompile')
    expect(title).toContain('app.apk')
    expect(body).toBe('已完成')
  })

  // ──── operation_complete: all backend payload shapes ────

  it('13. operation_complete with analyze payload (package_name etc) sets result when provided by caller', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running' })
    // PackagePage's onComplete converts analyze payload via renderApkInfo before calling transition
    store.transition(task.id, 'operation_complete', { result: '<div>analyzed html</div>' })
    expect(task.status).toBe('completed')
    expect(task.phase).toBe('finished')
    expect(task.result).toBe('<div>analyzed html</div>')
    expect(task.outputPath).toBe('')  // analyze has no output path
  })

  it('14. operation_complete with output_dir (decompile) sets outputPath', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running' })
    store.transition(task.id, 'operation_complete', { output_dir: '/out/decoded' })
    expect(task.outputPath).toBe('/out/decoded')
    expect(task.result).toBe('')
  })

  it('15. operation_complete with output_apk (recompile) sets outputPath', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running' })
    store.transition(task.id, 'operation_complete', { output_apk: '/out/recompiled.apk' })
    expect(task.outputPath).toBe('/out/recompiled.apk')
  })

  it('16. operation_complete with apk_path (sign) sets outputPath', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'operation', status: 'running' })
    store.transition(task.id, 'operation_complete', { apk_path: '/out/signed.apk' })
    expect(task.outputPath).toBe('/out/signed.apk')
  })

  it('12. unknown event is silently ignored (no throw, no mutation)', () => {
    const store = useTaskStore()
    const task = makeTask(store, { phase: 'idle', status: 'queued' })
    const snapshot = { phase: task.phase, status: task.status, progress: task.progress }

    expect(() => store.transition(task.id, 'unknown_event' as any)).not.toThrow()

    expect(task.phase).toBe(snapshot.phase)
    expect(task.status).toBe(snapshot.status)
    expect(task.progress).toBe(snapshot.progress)
  })
})
