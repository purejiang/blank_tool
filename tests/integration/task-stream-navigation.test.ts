/**
 * Integration tests: TaskStreamService + taskStore resilience when
 * PackagePage is unmounted (component gone, but global service survives).
 *
 * These tests prove the core fix: stream events received while the
 * component is not rendered are still processed by the global
 * TaskStreamService and correctly update taskStore state.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from '@stores/taskStore'
import TaskStreamService from '@services/TaskStreamService'
import type { TaskCallbacks } from '@services/TaskStreamService'

// ------------------------------------------------------------------
// Mock helpers
// ------------------------------------------------------------------

let streamHandler: ((data: any) => void) | null = null
let subscribeCount = 0

function setupMocks() {
  subscribeCount = 0
  streamHandler = null
  ;(window as any).electronAPI = {
    onStreamEvent: (cb: (data: any) => void) => {
      streamHandler = cb
      subscribeCount++
      return () => {
        streamHandler = null
      }
    },
    callBackendAPI: vi.fn().mockResolvedValue({}),
    appConfig: { get: vi.fn().mockResolvedValue(false) },
    showSystemNotification: vi.fn().mockResolvedValue(true),
    downloadFile: vi.fn(),
    cancelApkTask: vi.fn().mockResolvedValue({ cancelled: true }),
  }
}

/** Fire a stream event into the service via the mocked onStreamEvent callback. */
function fireStreamEvent(event: any) {
  if (!streamHandler) throw new Error('onStreamEvent not subscribed — call service.initialize() first')
  streamHandler(event)
}

// ------------------------------------------------------------------
// Helper: set up callbacks that use taskStore.transition (mimics executeTask)
// ------------------------------------------------------------------

function setTransitionCallbacks(service: TaskStreamService, taskId: number, store: ReturnType<typeof useTaskStore>) {
  const callbacks: TaskCallbacks = {
    onDownloadProgress: (progress: number, downloaded: number, total: number, speed: number) => {
      store.transition(taskId, 'download_progress', { progress, downloaded, total, speed })
    },
    onComplete: (payload: any, phase: string) => {
      if (phase === 'download') {
        store.transition(taskId, 'download_complete', payload)
      } else {
        // Mimic PackagePage's onComplete: extract operation-specific fields
        const transitionPayload: any = {}
        if (payload?.output_dir) transitionPayload.output_dir = payload.output_dir
        if (payload?.output_apk) transitionPayload.output_apk = payload.output_apk
        if (payload?.apk_path) transitionPayload.apk_path = payload.apk_path
        if (payload?.result) transitionPayload.result = payload.result
        store.transition(taskId, 'operation_complete', transitionPayload)
      }
    },
    onError: (msg: string) => {
      store.transition(taskId, 'operation_error', { message: msg })
    },
    onCancelled: () => {
      store.transition(taskId, 'cancel_ack')
    },
  }
  service.setCallbacks(String(taskId), callbacks)
}

// ------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------

describe('task-stream navigation resilience', () => {
  let service: TaskStreamService

  beforeEach(async () => {
    setActivePinia(createPinia())
    localStorage.clear()
    setupMocks()

    service = new TaskStreamService()
    await service.initialize()
  })

  afterEach(() => {
    service.destroy()
    vi.restoreAllMocks()
  })

  // Test 1: URL task — download phase completes, then operation phase
  // completes while "unmounted". Single bind survives across both phases
  // (no re-bind needed — auto-unbind only fires after terminal operation phase).
  it('1. URL task completes across both phases while unmounted', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'url',
      url: 'https://example.com/app.apk',
      filePath: '',
      fileName: 'app.apk',
      operation: 'install',
      operationLabel: 'Install',
    })

    // --- Phase 1: Download ---
    service.bindTask(String(task.id))
    setTransitionCallbacks(service, task.id, store)
    store.transition(task.id, 'start_download')
    service.setPhase(String(task.id), 'download')

    // Simulate backend pushing download-complete (user navigated away from PackagePage)
    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: { file_path: '/downloads/app.apk', size: 1024000 },
      },
    })

    // Verify download-phase state
    expect(task.filePath).toBe('/downloads/app.apk')
    expect(task.progress).toBe(100)
    expect(task.phase).toBe('download')
    // --- Phase 2: Operation (single bind from phase 1 still active) ---
    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: { output_dir: '/out/decompiled', result: 'Decompiled successfully' },
      },
    })

    // Verify final state
    expect(task.status).toBe('completed')
    expect(task.phase).toBe('finished')
    expect(task.progress).toBe(100)
    expect(task.outputPath).toBe('/out/decompiled')
    expect(task.result).toBe('Decompiled successfully')
    expect(task.finishedAt).toBeGreaterThan(0)
  })

  // Test 2: Local task — operation completes with outputPath
  it('2. local task completes operation phase while unmounted → outputPath populated', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'local',
      filePath: '/local/app.apk',
      fileName: 'app.apk',
      operation: 'decompile',
      operationLabel: 'Decompile',
    })

    service.bindTask(String(task.id))
    setTransitionCallbacks(service, task.id, store)
    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: { output_dir: '/out/decompiled_app', result: 'Done' },
      },
    })

    expect(task.status).toBe('completed')
    expect(task.phase).toBe('finished')
    expect(task.outputPath).toBe('/out/decompiled_app')
    expect(task.result).toBe('Done')
    expect(task.error).toBe('')
  })

  // Test 3: Error event during unmount → task failed with error message
  it('3. error event during unmount → task status = failed', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'local',
      filePath: '/tmp/app.apk',
      fileName: 'app.apk',
      operation: 'resign',
      operationLabel: 'Resign',
    })

    service.bindTask(String(task.id))
    setTransitionCallbacks(service, task.id, store)
    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'error',
        task_id: String(task.id),
        payload: { message: 'Disk full — cannot write output' },
      },
    })

    expect(task.status).toBe('failed')
    expect(task.phase).toBe('finished')
    expect(task.error).toBe('Disk full — cannot write output')
    expect(task.finishedAt).toBeGreaterThan(0)
  })

  // Test 4: Cancel event during unmount → task cancelled
  it('4. cancel event during unmount → task status = cancelled', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'local',
      filePath: '/tmp/app.apk',
      fileName: 'app.apk',
      operation: 'analyze',
      operationLabel: 'Analyze',
    })

    service.bindTask(String(task.id))
    setTransitionCallbacks(service, task.id, store)
    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'cancelled',
        task_id: String(task.id),
        payload: { task_id: String(task.id) },
      },
    })

    expect(task.status).toBe('cancelled')
    expect(task.phase).toBe('finished')
    expect(task.finishedAt).toBeGreaterThan(0)
  })

  // Test 5: Cross-task isolation — events for wrong task_id do not affect bound task
  it('5. events for task_id=2 do not affect task_id=1', async () => {
    const store = useTaskStore()
    const task1 = store.createTask({
      source: 'local',
      filePath: '/app1.apk',
      fileName: 'app1.apk',
      operation: 'decompile',
      operationLabel: 'Decompile 1',
    })
    const task2 = store.createTask({
      source: 'local',
      filePath: '/app2.apk',
      fileName: 'app2.apk',
      operation: 'recompile',
      operationLabel: 'Recompile 2',
    })

    // Bind task 1 only
    service.bindTask(String(task1.id))
    const onCompleteSpy = vi.fn()
    service.setCallbacks(String(task1.id), {
      onComplete: onCompleteSpy,
      onError: vi.fn(),
      onCancelled: vi.fn(),
    })
    store.transition(task1.id, 'start_operation')
    service.setPhase(String(task1.id), 'operation')

    // Fire event for task 2 (unbound)
    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task2.id),
        payload: { output_dir: '/hacked' },
      },
    })

    // Task 1 should be completely unaffected
    expect(onCompleteSpy).not.toHaveBeenCalled()
    expect(task1.status).toBe('running')
    expect(task1.phase).toBe('operation')
    expect(task1.outputPath).toBe('')
    // Task 2 also unaffected (not bound in service)
    expect(task2.status).toBe('queued')
  })

  // Test 6: Latch — complete event arrives before waitForPhase
  it('6. latch pattern: complete before waitForPhase → resolves immediately', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'url',
      url: 'https://example.com/app.apk',
      filePath: '',
      fileName: 'app.apk',
      operation: 'install',
      operationLabel: 'Install',
    })

    service.bindTask(String(task.id))

    // Fire complete BEFORE any transition (simulates race condition)
    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: { file_path: '/dl/app.apk', size: 2048 },
      },
    })

    // waitForPhase should resolve immediately (latch hit)
    const result = await service.waitForPhase(String(task.id), 'download')
    expect(result).toEqual({ file_path: '/dl/app.apk', size: 2048 })
  })

  // Test 7: Error event rejects even with no callbacks set
  it('7. error event without callbacks → waitForPhase rejects', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'local',
      filePath: '/app.apk',
      fileName: 'app.apk',
      operation: 'analyze',
      operationLabel: 'Analyze',
    })

    service.bindTask(String(task.id))
    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    const phasePromise = service.waitForPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'error',
        task_id: String(task.id),
        payload: { message: 'Backend timeout' },
      },
    })

    await expect(phasePromise).rejects.toThrow('Backend timeout')
    expect(task.status).toBe('running') // callbacks not set, so store not updated
  })

  // ==========================================================================
  // REGRESSION TEST: multi-phase task must complete with single bindTask().
  //
  // Real executeTask() calls bindTask() ONCE per task and expects the service
  // to keep routing events across BOTH the download and operation phases.
  // Previously, auto-unbind fired after download complete, which silently
  // broke operation phase event routing.
  // ==========================================================================
  it('8. REGRESSION: single bind survives download→operation (no re-bind)', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'url',
      url: 'https://example.com/app.apk',
      filePath: '',
      fileName: 'app.apk',
      operation: 'decompile',
      operationLabel: 'Decompile',
    })

    // --- Single bind, mimicking real executeTask ---
    service.bindTask(String(task.id))
    setTransitionCallbacks(service, task.id, store)

    // --- Download phase ---
    store.transition(task.id, 'start_download')
    service.setPhase(String(task.id), 'download')

    fireStreamEvent({
      data: {
        type: 'progress',
        task_id: String(task.id),
        payload: { progress: 50, downloaded: 512, total: 1024, speed: 100 },
      },
    })
    expect(task.progress).toBe(50)

    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: { file_path: '/dl/app.apk', size: 1024 },
      },
    })
    expect(task.filePath).toBe('/dl/app.apk')

    // --- Operation phase (NO re-bind — this is the regression scenario) ---
    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: { output_dir: '/out/decompiled' },
      },
    })

    // Task must reach terminal state
    expect(task.status).toBe('completed')
    expect(task.phase).toBe('finished')
    expect(task.outputPath).toBe('/out/decompiled')
    expect(task.finishedAt).toBeGreaterThan(0)
  })

  // ==========================================================================
  // REGRESSION TEST: analyze tasks must render result HTML across phase transition.
  // Backend sends {package_name, permissions, ...} — NO output_dir/result field.
  // PackagePage's onComplete converts it via renderApkInfo before calling transition.
  // ==========================================================================
  it('9. REGRESSION: analyze task renders result HTML across phase transition', async () => {
    const store = useTaskStore()
    const task = store.createTask({
      source: 'local',
      filePath: '/app.apk',
      fileName: 'app.apk',
      operation: 'analyze',
      operationLabel: 'Analyze',
    })

    service.bindTask(String(task.id))
    // Simulate a callback that mimics PackagePage's renderApkInfo conversion
    service.setCallbacks(String(task.id), {
      onComplete: (payload: any, phase: string) => {
        if (phase === 'download') return
        const t: any = {}
        if (payload?.package_name) t.result = `<div class="analysis">${payload.package_name}</div>`
        store.transition(task.id, 'operation_complete', t)
      },
      onError: vi.fn(),
      onCancelled: vi.fn(),
    })

    store.transition(task.id, 'start_operation')
    service.setPhase(String(task.id), 'operation')

    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: String(task.id),
        payload: {
          package_name: 'com.example.app',
          application_label: 'Example',
          permissions: ['android.permission.INTERNET'],
          native_libs: [],
        },
      },
    })

    expect(task.status).toBe('completed')
    expect(task.result).toBe('<div class="analysis">com.example.app</div>')
    expect(task.outputPath).toBe('')
  })
})
