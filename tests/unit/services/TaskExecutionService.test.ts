import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  enqueueTask,
  queueStats,
  MAX_CONCURRENT,
  __resetQueue,
} from '@/renderer/services/TaskExecutionService'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>(r => { resolve = r })
  return { promise, resolve }
}

describe('TaskExecutionService', () => {
  beforeEach(() => {
    __resetQueue()
  })

  it('runs at most MAX_CONCURRENT tasks concurrently', async () => {
    let running = 0
    let peak = 0
    const makeRunner = () => async () => {
      running++
      peak = Math.max(peak, running)
      await new Promise(r => setTimeout(r, 5))
      running--
    }
    for (let i = 0; i < 12; i++) enqueueTask(i, makeRunner())

    await vi.waitFor(() => {
      expect(queueStats()).toEqual({ waiting: 0, active: 0 })
    })
    expect(peak).toBe(MAX_CONCURRENT)
  })

  it('starts waiting tasks in FIFO order as slots free', async () => {
    const order: number[] = []
    const gates = Array.from({ length: MAX_CONCURRENT }, deferred)
    for (let i = 0; i < MAX_CONCURRENT; i++) {
      enqueueTask(i, async () => { order.push(i); await gates[i].promise })
    }
    for (let i = MAX_CONCURRENT; i < MAX_CONCURRENT + 3; i++) {
      enqueueTask(i, async () => { order.push(i) })
    }
    // First MAX_CONCURRENT start immediately in enqueue order
    expect(order).toEqual([0, 1, 2])

    gates.forEach(g => g.resolve())
    await vi.waitFor(() => {
      expect(order).toEqual([0, 1, 2, 3, 4, 5])
    })
  })

  it('replaces a waiting duplicate entry for the same task id', async () => {
    const gates = Array.from({ length: MAX_CONCURRENT }, deferred)
    for (let i = 0; i < MAX_CONCURRENT; i++) {
      enqueueTask(i, async () => { await gates[i].promise })
    }
    const runA = vi.fn()
    const runB = vi.fn()
    enqueueTask(99, async () => { runA(); await Promise.resolve() })
    enqueueTask(99, async () => { runB(); await Promise.resolve() })
    // Only the replacement stays in the queue
    expect(queueStats().waiting).toBe(1)

    gates[0].resolve()
    await vi.waitFor(() => {
      expect(runB).toHaveBeenCalledTimes(1)
    })
    expect(runA).not.toHaveBeenCalled()
  })

  it('runner rejection does not break the queue', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    enqueueTask(1, async () => { throw new Error('boom') })
    const ran = vi.fn()
    enqueueTask(2, async () => { ran() })

    await vi.waitFor(() => {
      expect(ran).toHaveBeenCalledTimes(1)
      // finally 中 active-- 晚一个微任务，一并等待
      expect(queueStats()).toEqual({ waiting: 0, active: 0 })
    })
    errSpy.mockRestore()
  })
})
