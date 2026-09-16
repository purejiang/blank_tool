import { ipcMain, WebContents, IpcMainInvokeEvent } from 'electron';
import log from 'electron-log';
import { ChildProcessWithoutNullStreams } from 'child_process';
import { IPC_CHANNELS, IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import type { BackendApiRequest, BackendStdioMessage, BackendEventMessage, BackendResponse, JsonObject } from '../../shared/ipc/protocol';
import { getConfigValue } from '../stores/appStore';
import { broadcastToAllWindows } from '../utils/broadcast';
import { isProcessWritable } from '../python/processHealth';

interface CallbackInfo {
    resolve: (value: unknown) => void;
    reject: (reason?: any) => void;
    sender: WebContents;
    process: ChildProcessWithoutNullStreams;
    method: string;
    resolved?: boolean;
    stream_id?: string;
    task_id?: string;
}

function isBackendEventMessage(message: BackendStdioMessage): message is BackendEventMessage {
    return (message as BackendEventMessage).type === 'event';
}

function isBackendResponse(message: BackendStdioMessage): message is BackendResponse {
    return typeof (message as BackendResponse).id !== 'undefined';
}

export const createErrorResponse = (message: string, code: number = -32603) => ({
    type: 'error' as const,
    payload: { code, message }
});

/**
 * Emit a synthetic terminal `error` event for a stream whose transport died
 * (per-request timeout fired or the backend process exited) so renderer
 * promises settled only by a terminal event cannot hang forever. Shaped like
 * the backend's own error events ({ type, payload, task_id }) so the renderer
 * services routing by `data.task_id` handle it verbatim. Never sent on the
 * logcat dedicated channels. No-op when the stream was never established or
 * the sender is gone.
 */
function emitSyntheticStreamTerminal(callbackInfo: CallbackInfo, message: string, code: number): void {
    if (!callbackInfo.stream_id || callbackInfo.sender.isDestroyed()) {
        return;
    }
    const data: JsonObject = { type: 'error', payload: { code, message } };
    if (callbackInfo.task_id !== undefined) {
        data.task_id = callbackInfo.task_id;
    }
    callbackInfo.sender.send(IPC_CHANNEL_NAMES.streamEvent, {
        stream_id: callbackInfo.stream_id,
        data
    });
}

export function setupCommandHandlers(
    getPythonProcess: () => ChildProcessWithoutNullStreams | null,
    ensurePythonProcess?: () => Promise<ChildProcessWithoutNullStreams | null>,
    requestTimeout: number | (() => number) = 300000
): void {
    const requestCallbacks = new Map<string | number, CallbackInfo>();
    const attachedProcesses = new WeakSet<ChildProcessWithoutNullStreams>();

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

            lines.forEach(message => {
                const msg = message.trim();
                if (!msg) return;
                if (!msg.startsWith('{')) return;
                try {
                    const response = JSON.parse(msg) as BackendStdioMessage;

                    if (isBackendEventMessage(response)) {
                        broadcastToAllWindows(response.event, response.data);
                        return;
                    }

                    if (isBackendResponse(response)) {
                        if (requestCallbacks.has(response.id)) {
                            const callbackInfo = requestCallbacks.get(response.id)!;
                            if (callbackInfo.process !== pythonProcess) {
                                return;
                            }
                            const { resolve, reject, sender } = callbackInfo;

                            if (response.finished === false) {
                                // Streaming event — forward to renderer regardless of result type
                                const result = (response.result || {}) as JsonObject;
                                // Remember the stream identity so a later
                                // timeout/backend-exit can synthesize a
                                // terminal event. The INIT carries it inside
                                // `result` ({ stream_id }, no `type`); typed
                                // events carry it at the top level.
                                if (typeof response.stream_id === 'string') {
                                    callbackInfo.stream_id = response.stream_id;
                                } else if (typeof result.stream_id === 'string') {
                                    callbackInfo.stream_id = result.stream_id;
                                }
                                const resultType = typeof result.type === 'string' ? result.type : '';
                                if (resultType && sender && !sender.isDestroyed()) {
                                    // logcat streams (adb.logcat) keep their dedicated channels;
                                    // every other streaming request (download/apk/install/aab)
                                    // is forwarded verbatim to streamEvent so task log lines
                                    // (type:'log', carrying line + task_id) reach the renderer.
                                    const isLogcat = requestCallbacks.get(response.id)?.method === 'adb.logcat';
                                    if (isLogcat) {
                                        const channelMap: Record<string, string> = {
                                            'log': IPC_CHANNEL_NAMES.logcatOutput,
                                            'started': IPC_CHANNEL_NAMES.logcatStarted,
                                            'process_finished': IPC_CHANNEL_NAMES.logcatFinished
                                        };
                                        const channel = channelMap[resultType];
                                        if (channel) {
                                            const resultPayload = typeof result.payload === 'object' && result.payload !== null
                                                ? result.payload as JsonObject
                                                : {};
                                            const payload = {
                                                stream_id: response.stream_id,
                                                ...resultPayload
                                            };
                                            sender.send(channel, payload);
                                        } else {
                                            sender.send(IPC_CHANNEL_NAMES.streamEvent, {
                                                stream_id: response.stream_id,
                                                data: result
                                            });
                                        }
                                    } else {
                                        sender.send(IPC_CHANNEL_NAMES.streamEvent, {
                                            stream_id: response.stream_id,
                                            data: result
                                        });
                                    }
                                }

                                if (!callbackInfo.resolved) {
                                    // Only the streaming INIT ({stream_id}, no
                                    // `type` field) resolves the invoke. A first
                                    // streaming event can beat the init onto
                                    // stdout (worker-thread race in the backend);
                                    // resolving with a typed event envelope
                                    // (log/complete/…) would make the renderer's
                                    // unwrapBackendResponse misread it as an error.
                                    if (!resultType) {
                                        resolve(response.result);
                                        callbackInfo.resolved = true;
                                    }
                                }
                            } else if (response.result && (response.result as unknown as JsonObject).type === 'error') {
                                const errorPayload = ((response.result as unknown as JsonObject).payload) as JsonObject | undefined;
                                const message = (errorPayload?.message as string) || 'Unknown backend error';
                                reject(new Error(message));
                                requestCallbacks.delete(response.id);
                            } else {
                                if (!callbackInfo.resolved) {
                                    resolve(response.result);
                                }
                                requestCallbacks.delete(response.id);
                            }
                        }
                    }
                } catch (e) {
                    console.error('Error parsing JSON from Python:', e);
                }
            });
        });

        pythonProcess.on('close', () => {
            for (const [id, callbackInfo] of requestCallbacks.entries()) {
                if (callbackInfo.process === pythonProcess) {
                    // Streams of a dying backend must still get a terminal
                    // event, or the renderer's per-task promise hangs forever.
                    emitSyntheticStreamTerminal(callbackInfo, '后端服务已退出：任务已中断，请重试', -32002);
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

    ipcMain.handle(IPC_CHANNELS.callBackendApi.name, async (event: IpcMainInvokeEvent, request: BackendApiRequest) => {
        const pythonProcess = await getWritableProcess();
        log.info(`[trace ${request.id}] dispatching ${request.method}`);
        if (!pythonProcess) {
            return createErrorResponse('后端服务未运行', -32001);
        }

        return new Promise((resolve, reject) => {
            const wrappedResolve = (value: unknown) => {
                log.info(`[trace ${request.id}] resolved`);
                resolve(value);
            };
            const wrappedReject = (reason?: unknown) => {
                const message = reason instanceof Error ? reason.message : String(reason);
                log.info(`[trace ${request.id}] rejected: ${message}`);
                reject(reason);
            };
            const rawTaskId = (request.params as JsonObject | undefined)?.task_id;
            const callbackInfo: CallbackInfo = { resolve: wrappedResolve, reject: wrappedReject, sender: event.sender, process: pythonProcess, method: request.method };
            if (typeof rawTaskId === 'string' || typeof rawTaskId === 'number') {
                callbackInfo.task_id = String(rawTaskId);
            }
            requestCallbacks.set(request.id, callbackInfo);

            try {
                if (request.method === 'download.file') {
                    request.params = { ...(request.params ?? {}), use_proxy: getConfigValue('useProxyForDownload') === true };
                }
                const payload = JSON.stringify(request) + '\n';
                const success = pythonProcess.stdin.write(payload);
                if (!success && pythonProcess.stdin && !pythonProcess.stdin.destroyed) {
                    pythonProcess.stdin.once('drain', () => {});
                }
            } catch (err) {
                requestCallbacks.delete(request.id);
                const message = err instanceof Error ? err.message : String(err);
                resolve(createErrorResponse(`发送请求失败: ${message}`, -32002));
            }

            setTimeout(() => {
                if (requestCallbacks.has(request.id)) {
                    const callbackInfo = requestCallbacks.get(request.id);
                    if (callbackInfo) {
                        // The invoke was already resolved by the streaming
                        // init — the timeout envelope below is a no-op for
                        // the renderer. Emit the synthetic terminal BEFORE
                        // the entry is deleted, or the stream's terminal
                        // event never reaches the renderer.
                        emitSyntheticStreamTerminal(callbackInfo, '请求超时：任务可能仍在后台执行，请查看日志后重试', -32003);
                    }
                    requestCallbacks.delete(request.id);
                    log.info(`[trace ${request.id}] timed out`);
                    resolve(createErrorResponse('请求超时', -32003));
                }
            }, typeof requestTimeout === 'function' ? requestTimeout() : requestTimeout);
        });
    });
}
