import { ipcMain, BrowserWindow, WebContents, IpcMainInvokeEvent } from 'electron';
import { ChildProcessWithoutNullStreams } from 'child_process';
import { IPC_CHANNELS, IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import type { BackendApiRequest, BackendStdioMessage, BackendEventMessage, BackendResponse, JsonObject } from '../../shared/ipc/protocol';

interface CallbackInfo {
    resolve: (value: unknown) => void;
    reject: (reason?: any) => void;
    sender: WebContents;
    process: ChildProcessWithoutNullStreams;
    resolved?: boolean;
}

function isBackendEventMessage(message: BackendStdioMessage): message is BackendEventMessage {
    return (message as BackendEventMessage).type === 'event';
}

function isBackendResponse(message: BackendStdioMessage): message is BackendResponse {
    return typeof (message as BackendResponse).id !== 'undefined';
}

export function setupCommandHandlers(
    getPythonProcess: () => ChildProcessWithoutNullStreams | null,
    ensurePythonProcess?: () => Promise<ChildProcessWithoutNullStreams | null>,
    requestTimeout = 300000
): void {
    const requestCallbacks = new Map<string | number, CallbackInfo>();
    const attachedProcesses = new WeakSet<ChildProcessWithoutNullStreams>();

    const createErrorResponse = (message: string) => ({
        type: 'error',
        error: { message }
    });

    const isBackendWritable = (pythonProcess: ChildProcessWithoutNullStreams | null): boolean => {
        return Boolean(
            pythonProcess &&
            !pythonProcess.killed &&
            pythonProcess.exitCode === null &&
            pythonProcess.stdin &&
            !pythonProcess.stdin.destroyed &&
            !pythonProcess.stdin.writableEnded &&
            pythonProcess.stdin.writable
        );
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

            lines.forEach(message => {
                const msg = message.trim();
                if (!msg) return;
                if (!msg.startsWith('{')) return;
                try {
                    const response = JSON.parse(msg) as BackendStdioMessage;

                    if (isBackendEventMessage(response)) {
                        const broadcast = (channel: string, payload: unknown) => {
                            BrowserWindow.getAllWindows().forEach(win => {
                                if (!win.isDestroyed()) {
                                    win.webContents.send(channel, payload);
                                }
                            });
                        };
                        broadcast(response.event, response.data);
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
                                const resultType = typeof result.type === 'string' ? result.type : '';
                                console.log('[main] streaming chunK:', JSON.stringify(response).substring(0, 200));
                                if (resultType && sender && !sender.isDestroyed()) {
                                    const channelMap: Record<string, string> = {
                                        'log': IPC_CHANNEL_NAMES.logcatOutput,
                                        'started': IPC_CHANNEL_NAMES.logcatStarted,
                                        'process_finished': IPC_CHANNEL_NAMES.logcatFinished
                                    };

                                    const channel = channelMap[resultType];
                                    console.log('[main] forwarding to channel:', channel, 'resultType:', resultType);
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
                                    console.log('[main] skipped forwarding, resultType:', resultType, 'sender:', !!sender, 'destroyed:', sender?.isDestroyed());
                                }

                                if (!callbackInfo.resolved) {
                                    resolve(response.result);
                                    callbackInfo.resolved = true;
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
                    callbackInfo.reject(new Error('后端服务已退出'));
                    requestCallbacks.delete(id);
                }
            }
        });
    };

    const getWritableProcess = async (): Promise<ChildProcessWithoutNullStreams | null> => {
        const current = getPythonProcess();
        bindProcess(current);
        if (isBackendWritable(current)) {
            return current;
        }
        if (ensurePythonProcess) {
            const ensured = await ensurePythonProcess();
            bindProcess(ensured);
            if (isBackendWritable(ensured)) {
                return ensured;
            }
        }
        return null;
    };

    ipcMain.handle(IPC_CHANNELS.callBackendApi.name, async (event: IpcMainInvokeEvent, request: BackendApiRequest) => {
        const pythonProcess = await getWritableProcess();
        if (!pythonProcess) {
            return createErrorResponse('后端服务未运行');
        }

        return new Promise((resolve, reject) => {
            requestCallbacks.set(request.id, { resolve, reject, sender: event.sender, process: pythonProcess });

            try {
                const payload = JSON.stringify(request) + '\n';
                const success = pythonProcess.stdin.write(payload);
                if (!success && pythonProcess.stdin && !pythonProcess.stdin.destroyed) {
                    pythonProcess.stdin.once('drain', () => {});
                }
            } catch (err) {
                requestCallbacks.delete(request.id);
                const message = err instanceof Error ? err.message : String(err);
                resolve(createErrorResponse(`发送请求失败: ${message}`));
            }

            setTimeout(() => {
                if (requestCallbacks.has(request.id)) {
                    requestCallbacks.delete(request.id);
                    resolve(createErrorResponse('请求超时'));
                }
            }, requestTimeout);
        });
    });
}
