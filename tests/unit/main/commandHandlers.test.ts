import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { ChildProcessWithoutNullStreams } from 'child_process'

const mockIpcHandle = vi.fn()
const mockGetAllWindows = vi.fn(() => [])

vi.mock('electron', () => ({
    ipcMain: { handle: mockIpcHandle },
    BrowserWindow: { getAllWindows: mockGetAllWindows },
}))

describe('createErrorResponse', () => {
    it('returns error shape with code and message when code is provided', async () => {
        const { createErrorResponse } = await import('@/main/ipc/commandHandlers')

        const result = createErrorResponse('后端服务未运行', -32001)

        expect(result).toEqual({
            type: 'error',
            payload: { code: -32001, message: '后端服务未运行' },
        })
    })

    it('uses default code -32603 (JSON-RPC internal error) when no code provided', async () => {
        const { createErrorResponse } = await import('@/main/ipc/commandHandlers')

        const result = createErrorResponse('未知错误')

        expect(result).toEqual({
            type: 'error',
            payload: { code: -32603, message: '未知错误' },
        })
    })

    it('has type narrowed to "error" literal via as const', async () => {
        const { createErrorResponse } = await import('@/main/ipc/commandHandlers')

        const result = createErrorResponse('test')

        // TypeScript would catch this at compile time — at runtime we assert the literal
        expect(result.type).toBe('error')
    })
})

// ---------------------------------------------------------------------------
// Cancel propagation on timeout
// ---------------------------------------------------------------------------

describe('setupCommandHandlers cancel-on-timeout', () => {
    let mockStdinWrite: ReturnType<typeof vi.fn>
    let mockPythonProcess: ChildProcessWithoutNullStreams

    beforeEach(() => {
        vi.useFakeTimers()
        vi.clearAllMocks()
        mockStdinWrite = vi.fn(() => true)

        mockPythonProcess = {
            stdin: {
                write: mockStdinWrite,
                writableEnded: false,
                writable: true,
                on: vi.fn(),
                once: vi.fn(),
                removeListener: vi.fn(),
                off: vi.fn(),
                addListener: vi.fn(),
                emit: vi.fn(),
                eventNames: vi.fn(() => []),
                getMaxListeners: vi.fn(() => 10),
                listenerCount: vi.fn(() => 0),
                listeners: vi.fn(() => []),
                prependListener: vi.fn(),
                prependOnceListener: vi.fn(),
                rawListeners: vi.fn(() => []),
                removeAllListeners: vi.fn(),
                setMaxListeners: vi.fn(),
                end: vi.fn(),
                cork: vi.fn(),
                uncork: vi.fn(),
                writableCorked: 0,
                writableFinished: false,
                writableHighWaterMark: 16384,
                writableLength: 0,
                writableNeedDrain: false,
                writableObjectMode: false,
                _write: vi.fn(),
                _writev: undefined,
                _destroy: vi.fn(),
                _final: vi.fn(),
                closed: false,
                errored: null,
                [Symbol.asyncDispose]: vi.fn(),
                compose: vi.fn(),
                pipe: vi.fn(),
                setDefaultEncoding: vi.fn(),
                unpipe: vi.fn(),
                writableCorkedRequested: false,
                _writableState: {} as any,
            } as any,
            stdout: { on: vi.fn() } as any,
            stderr: { on: vi.fn() } as any,
            killed: false,
            exitCode: null,
            on: vi.fn(),
            pid: 1234,
            connected: false,
            signalCode: null,
            spawnargs: [],
            spawnfile: 'python',
            channel: undefined,
        } as any
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('writes cancel JSON-RPC to stdin when request times out', async () => {
        const { setupCommandHandlers } = await import('@/main/ipc/commandHandlers')

        const getPythonProcess = vi.fn(() => mockPythonProcess)

        setupCommandHandlers(getPythonProcess, undefined, 300000)

        // Get the handler registered for call-backend-api
        const handler = mockIpcHandle.mock.calls.find(
            (c: any[]) => c[0] === 'call-backend-api',
        )![1]

        // Simulate renderer calling callBackendApi
        const event = { sender: { isDestroyed: () => false, send: vi.fn() } } as any
        const request = {
            id: 'req-123',
            method: 'workflow.run',
            params: { task_id: 'task-abc', template_name: 'my-wf' },
        }

        const resultPromise = handler(event, request)

        // Let microtasks process (the handler does await, stdin.write, then setTimeout)
        await vi.runAllTimersAsync()

        const result = await resultPromise

        // Verify cancel was written to Python stdin
        expect(mockStdinWrite).toHaveBeenCalledTimes(2) // 1 for the request, 1 for cancel
        const cancelCall = mockStdinWrite.mock.calls[1]?.[0] as string
        expect(cancelCall).toContain('request.cancel')
        expect(cancelCall).toContain('task-abc')

        const parsed = JSON.parse(cancelCall.trim())
        expect(parsed.method).toBe('request.cancel')
        expect(parsed.params.task_id).toBe('task-abc')

        // Verify the response is a timeout error
        expect(result).toEqual({
            type: 'error',
            payload: { code: -32003, message: '请求超时' },
        })
    })

    it('sends cancel with empty task_id when params has no task_id', async () => {
        const { setupCommandHandlers } = await import('@/main/ipc/commandHandlers')

        const getPythonProcess = vi.fn(() => mockPythonProcess)
        setupCommandHandlers(getPythonProcess, undefined, 300000)

        const handler = mockIpcHandle.mock.calls.find(
            (c: any[]) => c[0] === 'call-backend-api',
        )![1]

        const event = { sender: { isDestroyed: () => false, send: vi.fn() } } as any
        const request = {
            id: 'req-456',
            method: 'some.other',
            params: {},
        }

        const resultPromise = handler(event, request)
        await vi.runAllTimersAsync()
        await resultPromise

        const cancelCall = mockStdinWrite.mock.calls[1]?.[0] as string
        const parsed = JSON.parse(cancelCall.trim())
        expect(parsed.method).toBe('request.cancel')
        expect(parsed.params.task_id).toBe('')
    })
})
