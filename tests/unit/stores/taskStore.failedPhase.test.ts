import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from '@/renderer/stores/taskStore'

// Batch 4: failedPhase drives the "retry failed stage" button. These tests
// pin the transition behavior: recorded from the error payload, falls back
// to the task's live phase, and cleared by reset_for_retry.
describe('taskStore failedPhase tracking', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  function makeTask(store: ReturnType<typeof useTaskStore>) {
    return store.createTask({
      source: 'url',
      url: 'https://example.com/app.apk',
      filePath: '',
      fileName: 'app.apk',
      operation: 'install',
      operationLabel: 'Install',
    })
  }

  it('new tasks start queued with empty failedPhase', () => {
    const store = useTaskStore()
    const t = makeTask(store)
    expect(t.status).toBe('queued')
    expect(t.phase).toBe('idle')
    expect(t.failedPhase).toBe('')
  })

  it('records failedPhase from the error payload', () => {
    const store = useTaskStore()
    const t = makeTask(store)
    store.transition(t.id, 'start_download')
    store.transition(t.id, 'operation_error', { message: 'boom', failedPhase: 'download' })
    expect(store.tasks.find(x => x.id === t.id)?.failedPhase).toBe('download')
  })

  it('falls back to the live phase when payload has no failedPhase', () => {
    const store = useTaskStore()
    const t = makeTask(store)
    store.transition(t.id, 'start_operation')
    store.transition(t.id, 'operation_error', { message: 'boom' })
    expect(store.tasks.find(x => x.id === t.id)?.failedPhase).toBe('operation')
  })

  it('reset_for_retry clears failedPhase', () => {
    const store = useTaskStore()
    const t = makeTask(store)
    store.transition(t.id, 'start_operation')
    store.transition(t.id, 'operation_error', { message: 'boom' })
    expect(store.tasks.find(x => x.id === t.id)?.failedPhase).toBe('operation')

    store.transition(t.id, 'reset_for_retry')
    const reset = store.tasks.find(x => x.id === t.id)
    expect(reset?.failedPhase).toBe('')
    expect(reset?.status).toBe('queued')
  })
})
