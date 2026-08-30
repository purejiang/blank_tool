import { ipcMain, WebContents, IpcMainInvokeEvent } from 'electron';
import log from 'electron-log';
import { ChildProcessWithoutNullStreams } from 'child_process';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import { extractTaskId } from '../../shared/ipc/protocol';
import type { BackendApiRequest, BackendResponse, JsonObject } from '../../shared/ipc/protocol';
import { MAIN_BRIDGE_ERROR_CODES } from '../../shared/errors';
import { isProcessWritable } from '../python/processWritable';

interface CallbackInfo {
    resolve: (value: unknown) => void;
    reject: (reason?: any) => void;
    sender: WebContents;
    process: ChildProcessWithoutNullStreams;
    resolved?: boolean;
    timer?: ReturnType<typeof setTimeout>;
    taskId?: string;
}

function isBackendResponse(message: unknown): message is BackendResponse {
    return typeof (message as BackendResponse)?.id !== 'undefined';
}

export const createErrorResponse = (message: string, code: number = MAIN_BRIDGE_ERROR_CODES.INTERNAL_ERROR) => ({
    type: 'error' as const,
    payload: { code, message }
});

export function setupCommandHandlers(
    getPythonProcess: () => ChildProcessWithoutNullStreams | null,
    ensurePythonProcess?: () => Promise<ChildProcessWithoutNullStreams | null>,
    requestTimeout = 300000
): void {
    const requestCallbacks = new Map<string, CallbackInfo>();
    const attachedProcesses = new WeakSet<ChildProcessWithoutNullStreams>();

    const clearTimer = (callbackInfo: CallbackInfo) => {
        if (callbackInfo.timer) {
            clearTimeout(callbackInfo.timer);
            callbackInfo.timer = undefined;
        }
    };

    // Inactivity timeout: re-armed on every streaming frame, so a long-running
    // stream (e.g. decompile) is only cancelled after `requestTimeout` of silence,
    // not after `requestTimeout` of total runtime.
    const armTimeout = (requestId: string, callbackInfo: CallbackInfo) => {
        clearTimer(callbackInfo);
        if (!requestCallbacks.has(requestId)) {
            return;
        }
        callbackInfo.timer = setTimeout(() => {
            if (!requestCallbacks.has(requestId)) {
                return;
            }
            const cb = requestCallbacks.get(requestId)!;
            // Fire-and-forget cancel: signal the Python stream to stop via task_id.
            const taskId = cb.taskId || '';
            try {
                const cancelPayload = JSON.stringify({
                    id: `${requestId}-cancel`,
                    method: 'request.cancel',
                    params: { task_id: taskId },
                }) + '\n';
                if (cb.process.stdin && !cb.process.stdin.destroyed) {
                    cb.process.stdin.write(cancelPayload);
                }
            } catch (_err) {
                // Fire-and-forget: silently ignore write errors.
            }
            requestCallbacks.delete(requestId);
            log.info(`[trace ${requestId}] timed out`);
            cb.resolve(createErrorResponse('请求超时', MAIN_BRIDGE_ERROR_CODES.TIMEOUT));
        }, requestTimeout);
    };

    const bindProcess = (pythonProcess: ChildProcessWithoutNullStreams | null): void => {
        if (!pythonProcess || attachedProcesses.has(pythonProcess)) {
            return;
        }
        attachedProcesses.add(pythonProcess);
        let dataBuffer = '';

        pythonProcess.stdout.on('data', (data: Buffer) => {
            dataBuffer += data.toString();
            const lines = dataBuffer.split('\n');
            dataBuffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) {
                    continue;
                }
                try {
                    const response = JSON.parse(line) as unknown;
                    if (!isBackendResponse(response)) {
                        continue;
                    }
                    const callbackInfo = requestCallbacks.get(response.id);
                    if (!callbackInfo || callbackInfo.process !== pythonProcess) {
                        // Late response or fire-and-forget cancel ack — ignore.
                        continue;
                    }
                    const { resolve, reject, sender } = callbackInfo;

                    if (response.finished === false) {
                        // Streaming frame — forward to renderer and re-arm the timeout.
                        const result = (response.result || {}) as JsonObject;
                        if (result.task_id) {
                            callbackInfo.taskId = String(result.task_id);
                        }
                        const resultType = typeof result.type === 'string' ? result.type : '';
                        if (resultType && sender && !sender.isDestroyed()) {
                            sender.send(IPC_CHANNEL_NAMES.streamEvent, {
                                stream_id: response.stream_id,
                                data: result
                            });
                        }
                        if (!callbackInfo.resolved) {
                            resolve(response.result);
                            callbackInfo.resolved = true;
                        }
                        armTimeout(response.id, callbackInfo);
                    } else if (response.result && (response.result as unknown as JsonObject).type === 'error') {
                        clearTimer(callbackInfo);
                        const errorPayload = (response.result as unknown as JsonObject).payload as JsonObject | undefined;
                        const message = (errorPayload?.message as string) || 'Unknown backend error';
                        reject(new Error(message));
                        requestCallbacks.delete(response.id);
                    } else {
                        clearTimer(callbackInfo);
                        if (!callbackInfo.resolved) {
                            resolve(response.result);
                        }
                        requestCallbacks.delete(response.id);
                    }
                } catch (e) {
                    console.error('Error parsing JSON from Python:', e);
                }
            }
        });

        pythonProcess.on('close', () => {
            for (const [id, callbackInfo] of requestCallbacks.entries()) {
                if (callbackInfo.process === pythonProcess) {
                    clearTimer(callbackInfo);
                    callbackInfo.reject(new Error('后端服务已退出'));
                    requestCallbacks.delete(id);
                }
            }
        });
    };

    const getWritableProcess = async (): Promise<ChildProcessWithoutNullStreams | null> => {
        const current = getPythonProcess();
        bindProcess(current);
        if (isProcessWritable(current)) {
            return current;
        }
        if (ensurePythonProcess) {
            const ensured = await ensurePythonProcess();
            bindProcess(ensured);
            if (isProcessWritable(ensured)) {
                return ensured;
            }
        }
        return null;
    };

    ipcMain.handle(IPC_CHANNEL_NAMES.callBackendApi, async (event: IpcMainInvokeEvent, request: BackendApiRequest) => {
        const pythonProcess = await getWritableProcess();
        const requestId = String(request.id);
        log.info(`[trace ${requestId}] dispatching ${request.method}`);
        if (!pythonProcess) {
            return createErrorResponse('后端服务未运行', MAIN_BRIDGE_ERROR_CODES.BACKEND_NOT_RUNNING);
        }

        return new Promise((resolve, reject) => {
            const wrappedResolve = (value: unknown) => {
                log.info(`[trace ${requestId}] resolved`);
                resolve(value);
            };
            const wrappedReject = (reason?: unknown) => {
                const message = reason instanceof Error ? reason.message : String(reason);
                log.info(`[trace ${requestId}] rejected: ${message}`);
                reject(reason);
            };
            const callbackInfo: CallbackInfo = {
                resolve: wrappedResolve,
                reject: wrappedReject,
                sender: event.sender,
                process: pythonProcess,
                taskId: extractTaskId(request.params),
            };
            requestCallbacks.set(requestId, callbackInfo);

            try {
                const payload = JSON.stringify({ ...request, id: requestId }) + '\n';
                const success = pythonProcess.stdin.write(payload);
                if (!success && pythonProcess.stdin && !pythonProcess.stdin.destroyed) {
                    pythonProcess.stdin.once('drain', () => {});
                }
            } catch (err) {
                requestCallbacks.delete(requestId);
                const message = err instanceof Error ? err.message : String(err);
                resolve(createErrorResponse(`发送请求失败: ${message}`, MAIN_BRIDGE_ERROR_CODES.SEND_FAILED));
                return;
            }

            armTimeout(requestId, callbackInfo);
        });
    });
}
