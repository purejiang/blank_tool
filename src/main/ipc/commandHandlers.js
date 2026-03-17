import { ipcMain, BrowserWindow } from 'electron';

export function setupCommandHandlers(pythonProcess) {
    const requestCallbacks = new Map();
    let dataBuffer = '';

    pythonProcess.stdout.on('data', (data) => {
        dataBuffer += data.toString();
        const lines = dataBuffer.split('\n');
        
        // The last part might be incomplete, keep it in the buffer
        dataBuffer = lines.pop();

        lines.forEach(message => {
            const msg = message.trim();
            if (!msg) return;
            if (!msg.startsWith('{')) return;
            try {
                const response = JSON.parse(msg);
                
                // Handle global events (without ID or with special type)
                if (response.type === 'event') {
                    const broadcast = (channel, payload) => {
                        BrowserWindow.getAllWindows().forEach(win => {
                            if (!win.isDestroyed()) {
                                win.webContents.send(channel, payload);
                            }
                        });
                    };
                    broadcast(response.event, response.data);
                    return;
                }

                // Handle Responses (Sync or Stream)
                if (response && typeof response.id !== 'undefined') {
                    if (requestCallbacks.has(response.id)) {
                        const callbackInfo = requestCallbacks.get(response.id);
                        const { resolve, reject, sender } = callbackInfo;
                        
                        if (response.error) {
                            reject(new Error(response.error.message));
                            requestCallbacks.delete(response.id);
                        } else if (response.finished === false) {
                            // Stream Chunk
                            const result = response.result || {};
                            
                            // Map result type to IPC channel if possible
                            if (result.type && sender && !sender.isDestroyed()) {
                                const channelMap = {
                                    'log': 'logcat-output',
                                    'started': 'logcat-started',
                                    'process_finished': 'logcat-finished',
                                    'error': 'logcat-error'
                                };

                                const channel = channelMap[result.type];
                                if (channel) {
                                    const payload = { 
                                        stream_id: response.stream_id, 
                                        ...result.payload 
                                    };
                                    sender.send(channel, payload);
                                } else {
                                    sender.send('stream-event', { 
                                        stream_id: response.stream_id, 
                                        data: result 
                                    });
                                }
                            }
                            
                            // If this is the first chunk/response, resolve the promise so the caller isn't blocked
                            if (!callbackInfo.resolved) {
                                resolve(response.result);
                                callbackInfo.resolved = true;
                            }
                        } else {
                            // Finished = True
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

    ipcMain.handle('call-backend-api', async (event, request) => {
        if (!pythonProcess || pythonProcess.killed) {
            return { 
                type: 'error', 
                error: { message: '后端服务未运行' } 
            };
        }

        return new Promise((resolve, reject) => {
            // Store sender to send stream updates back to the caller
            requestCallbacks.set(request.id, { resolve, reject, sender: event.sender });
            
            try {
                const success = pythonProcess.stdin.write(JSON.stringify(request) + '\n');
                if (!success) {
                    requestCallbacks.delete(request.id);
                    resolve({ 
                        type: 'error', 
                        error: { message: '无法发送请求到后端服务' } 
                    });
                }
            } catch (err) {
                requestCallbacks.delete(request.id);
                resolve({ 
                    type: 'error', 
                    error: { message: `发送请求失败: ${err.message}` } 
                });
            }

            // 设置超时 (30秒)
            setTimeout(() => {
                if (requestCallbacks.has(request.id)) {
                    requestCallbacks.delete(request.id);
                    resolve({ 
                        type: 'error', 
                        error: { message: '请求超时' } 
                    });
                }
            }, 30000);
        });
    });
}
