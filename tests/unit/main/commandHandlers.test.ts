/**
 * commandHandlers — transport-level behaviour of the call-backend-api handler.
 *
 * Pins the terminal-event contract for streaming requests (TDD Stage B):
 * when a stream outlives its per-request timeout or the Python backend exits
 * mid-stream, the main process must emit exactly ONE synthetic terminal
 * `error` event on `stream-event` — shaped like the backend's own error
 * events (`{ type, payload, task_id }`) so the renderer services that route
 * by `data.task_id` (TaskStreamService / AutomationService / RecordingService)
 * can settle their promises. Behaviours that must not change (pre-init
 * timeout, non-streaming timeout, logcat dedicated channels, close-reject of
 * pending non-streaming invokes) are pinned too.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { EventEmitter } from 'node:events'
import type { ChildProcessWithoutNullStreams } from 'node:child_process'
import { IPC_CHANNELS, IPC_CHANNEL_NAMES } from '@/shared/ipc/channels'
import { setupCommandHandlers } from '@/main/ipc/commandHandlers'

const mocks = vi.hoisted(() => {
    const ipcHandlers = new Map<string, (event: unknown, request: unknown) => Promise<unknown>>()
    return {
        ipcHandlers,
        ipcMain: {
            handle: (channel: string, handler: (event: unknown, request: unknown) => Promise<unknown>) => {
                ipcHandlers.set(channel, handler)
            },
        },
        getConfigValue: () => false,
        isProcessWritable: () => true,
        broadcastToAllWindows: () => undefined,
    }
})

vi.mock('electron', () => ({ ipcMain: mocks.ipcMain }))

vi.mock('electron-log', () => ({
    default: { info: () => undefined, warn: () => undefined, error: () => undefined },
}))

vi.mock('@/main/stores/appStore', () => ({ getConfigValue: mocks.getConfigValue }))

vi.mock('@/main/utils/broadcast', () => ({ broadcastToAllWindows: mocks.broadcastToAllWindows }))

vi.mock('@/main/python/processHealth', () => ({ isProcessWritable: mocks.isProcessWritable }))

const TIMEOUT_MS = 50

class FakeStdin extends EventEmitter {
    write = () => true
    once = () => undefined
    destroyed = false
    writableEnded = false
    writable = true
}

class FakePythonProcess extends EventEmitter {
    stdout = new EventEmitter()
    stdin = new FakeStdin()
    killed = false
    exitCode = null
}

interface FakeSender {
    send: ReturnType<typeof vi.fn>
    isDestroyed: () => boolean
}

function makeSender(): FakeSender {
    return { send: vi.fn(), isDestroyed: () => false }
}

function emitBackendLine(proc: FakePythonProcess, message: Record<string, unknown>): void {
    proc.stdout.emit('data', Buffer.from(JSON.stringify(message) + '\n'))
}

function streamEvents(sender: FakeSender): Array<[string, unknown]> {
    return sender.send.mock.calls.filter(
        (call: unknown[]) => call[0] === IPC_CHANNEL_NAMES.streamEvent
    ) as Array<[string, unknown]>
}

const sendCount = (sender: FakeSender): number => sender.send.mock.calls.length

let proc: FakePythonProcess
let handler: (event: unknown, request: unknown) => Promise<unknown>

beforeEach(() => {
    vi.useFakeTimers()
    mocks.ipcHandlers.clear()
    proc = new FakePythonProcess()
    setupCommandHandlers(
        () => proc as unknown as ChildProcessWithoutNullStreams,
        undefined,
        TIMEOUT_MS
    )
    handler = mocks.ipcHandlers.get(IPC_CHANNELS.callBackendApi.name)!
})

afterEach(() => {
    vi.useRealTimers()
})

describe('commandHandlers transport', () => {
    describe('streaming request that outlives its timeout', () => {
        it('emits exactly one synthetic terminal stream event after the init', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(0)

            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })
            expect(sender.send).not.toHaveBeenCalled()

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(streamEvents(sender)).toEqual([
                [IPC_CHANNEL_NAMES.streamEvent, {
                    stream_id: 'stream-1',
                    data: {
                        type: 'error',
                        task_id: 'task-1',
                        payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' },
                    },
                }],
            ])
        })

        it('still sends the synthetic terminal exactly once when typed events preceded the timeout', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            emitBackendLine(proc, { id: 'req-1', result: { type: 'progress', payload: { progress: 10 } }, stream_id: 'stream-1', finished: false })
            emitBackendLine(proc, { id: 'req-1', result: { type: 'progress', payload: { progress: 50 } }, stream_id: 'stream-1', finished: false })
            expect(streamEvents(sender)).toHaveLength(2)

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(streamEvents(sender)).toHaveLength(3)
            const [, terminal] = streamEvents(sender)[2]
            expect(terminal).toEqual({
                stream_id: 'stream-1',
                data: {
                    type: 'error',
                    task_id: 'task-1',
                    payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' },
                },
            })
        })

        it('stream events arriving after the timeout are still dropped (no second terminal)', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)
            const countAfterTimeout = sendCount(sender)

            emitBackendLine(proc, { id: 'req-1', result: { type: 'log', payload: { line: 'late' } }, stream_id: 'stream-1', finished: false })
            emitBackendLine(proc, { id: 'req-1', finished: true })

            expect(sendCount(sender)).toBe(countAfterTimeout)
        })

        it('two concurrent timed-out streams each emit their own single terminal (no cross-talk)', async () => {
            const senderA = makeSender()
            const senderB = makeSender()
            const promiseA = handler(
                { sender: senderA },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            const promiseB = handler(
                { sender: senderB },
                { id: 'req-2', method: 'download.file', params: { url: 'https://example.com/b.apk', task_id: 'task-2' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            emitBackendLine(proc, { id: 'req-2', result: { stream_id: 'stream-2' }, finished: false })
            await expect(promiseA).resolves.toEqual({ stream_id: 'stream-1' })
            await expect(promiseB).resolves.toEqual({ stream_id: 'stream-2' })

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(streamEvents(senderA)).toEqual([
                [IPC_CHANNEL_NAMES.streamEvent, {
                    stream_id: 'stream-1',
                    data: {
                        type: 'error',
                        task_id: 'task-1',
                        payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' },
                    },
                }],
            ])
            expect(streamEvents(senderB)).toEqual([
                [IPC_CHANNEL_NAMES.streamEvent, {
                    stream_id: 'stream-2',
                    data: {
                        type: 'error',
                        task_id: 'task-2',
                        payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' },
                    },
                }],
            ])
        })

        it('omits task_id from the synthetic envelope when the request params carry none', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(streamEvents(sender)).toHaveLength(1)
            const envelope = streamEvents(sender)[0][1] as { data: Record<string, unknown> }
            expect(envelope).toEqual({
                stream_id: 'stream-1',
                data: { type: 'error', payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' } },
            })
            expect(Object.prototype.hasOwnProperty.call(envelope.data, 'task_id')).toBe(false)
        })

        it('keeps only string/number task_ids (boolean or object task_id is omitted)', async () => {
            for (const badTaskId of [true, { n: 1 }]) {
                const sender = makeSender()
                const promise = handler(
                    { sender },
                    { id: 'req-1', method: 'download.file', params: { url: 'u', task_id: badTaskId as unknown as string } }
                )
                await vi.advanceTimersByTimeAsync(0)
                emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
                await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })
                await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

                expect(streamEvents(sender)).toHaveLength(1)
                const envelope = streamEvents(sender)[0][1] as { data: Record<string, unknown> }
                expect(Object.prototype.hasOwnProperty.call(envelope.data, 'task_id')).toBe(false)
            }
        })

        it('stringifies a numeric task_id into the synthetic envelope', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'u', task_id: 42 } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(streamEvents(sender)).toEqual([
                [IPC_CHANNEL_NAMES.streamEvent, {
                    stream_id: 'stream-1',
                    data: {
                        type: 'error',
                        task_id: '42',
                        payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' },
                    },
                }],
            ])
        })

        it('does not send the synthetic terminal to a destroyed sender (and does not throw)', async () => {
            const sender = makeSender()
            sender.isDestroyed = () => true
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'u', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(sender.send).not.toHaveBeenCalled()
        })

        it('emits the synthetic terminal for a request without params (no task_id key)', async () => {
            const sender = makeSender()
            const promise = handler({ sender }, { id: 'req-1', method: 'automation.run' })
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(streamEvents(sender)).toEqual([
                [IPC_CHANNEL_NAMES.streamEvent, {
                    stream_id: 'stream-1',
                    data: { type: 'error', payload: { code: -32003, message: '请求超时：任务可能仍在后台执行，请查看日志后重试' } },
                }],
            ])
        })
    })

    describe('backend exit mid-stream', () => {
        it('emits exactly one synthetic terminal stream event for a resolved streaming entry', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            proc.emit('close')

            expect(streamEvents(sender)).toEqual([
                [IPC_CHANNEL_NAMES.streamEvent, {
                    stream_id: 'stream-1',
                    data: {
                        type: 'error',
                        task_id: 'task-1',
                        payload: { code: -32002, message: '后端服务已退出：任务已中断，请重试' },
                    },
                }],
            ])
        })
    })

    describe('late timeout timer after a normal completion', () => {
        it('is a no-op once the stream finished and its entry was reaped', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'stream-1' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })

            // Normal completion: the terminal `finished:true` line reaps the
            // request entry (the invoke was already resolved by the init).
            emitBackendLine(proc, { id: 'req-1', finished: true })
            const sendsAfterCompletion = sendCount(sender)

            // The per-request timer now fires LATE. With the entry gone the
            // synthetic send must be skipped: no extra stream event, no
            // re-resolve with the timeout envelope, and nothing throws.
            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            expect(sendCount(sender)).toBe(sendsAfterCompletion)
            expect(streamEvents(sender)).toHaveLength(0)
            await expect(promise).resolves.toEqual({ stream_id: 'stream-1' })
        })
    })

    describe('behaviours that must not change', () => {
        it('timeout before the init resolves the error envelope (pre-init path unchanged)', async () => {
            const sender = makeSender()
            const promise = handler(
                { sender },
                { id: 'req-1', method: 'download.file', params: { url: 'https://example.com/a.apk', task_id: 'task-1' } }
            )
            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            await expect(promise).resolves.toEqual({ type: 'error', payload: { code: -32003, message: '请求超时' } })
            expect(sender.send).not.toHaveBeenCalled()
        })

        it('non-streaming request timeout resolves the error envelope (unchanged)', async () => {
            const sender = makeSender()
            const promise = handler({ sender }, { id: 'req-1', method: 'adb.devices', params: {} })
            await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1)

            await expect(promise).resolves.toEqual({ type: 'error', payload: { code: -32003, message: '请求超时' } })
            expect(sender.send).not.toHaveBeenCalled()
        })

        it('logcat stream events keep their dedicated channels (no streamEvent)', async () => {
            const sender = makeSender()
            const promise = handler({ sender }, { id: 'req-1', method: 'adb.logcat', params: { device_id: 'emu-5554' } })
            await vi.advanceTimersByTimeAsync(0)
            emitBackendLine(proc, { id: 'req-1', result: { stream_id: 'logcat-x' }, finished: false })
            await expect(promise).resolves.toEqual({ stream_id: 'logcat-x' })

            emitBackendLine(proc, { id: 'req-1', result: { type: 'log', payload: { line: 'I/Tag: hello' } }, stream_id: 'logcat-x', finished: false })
            emitBackendLine(proc, { id: 'req-1', result: { type: 'process_finished', payload: { code: 0 } }, stream_id: 'logcat-x', finished: false })

            expect(sender.send).toHaveBeenCalledWith(IPC_CHANNEL_NAMES.logcatOutput, { stream_id: 'logcat-x', line: 'I/Tag: hello' })
            expect(sender.send).toHaveBeenCalledWith(IPC_CHANNEL_NAMES.logcatFinished, { stream_id: 'logcat-x', code: 0 })
            expect(streamEvents(sender)).toHaveLength(0)
        })

        it('backend exit still rejects a pending non-streaming invoke', async () => {
            const sender = makeSender()
            const promise = handler({ sender }, { id: 'req-1', method: 'adb.devices', params: {} })
            await vi.advanceTimersByTimeAsync(0)

            proc.emit('close')

            await expect(promise).rejects.toThrow('后端服务已退出')
            expect(streamEvents(sender)).toHaveLength(0)
        })
    })
})
