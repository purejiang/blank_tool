import { ipcMain, BrowserWindow } from 'electron';

export function setupCommandHandlers(pythonProcess) {
    const requestCallbacks = new Map();

    pythonProcess.stdout.on('data', (data) => {
        const messages = data.toString().split('\n').filter(msg => msg.trim() !== '');
        messages.forEach(message => {
            const msg = message.trim();
            if (!msg.startsWith('{')) return;
            try {
                const response = JSON.parse(msg);
                if (response && response.type === 'event' && response.event) {
                    const broadcast = (channel, payload) => {
                        BrowserWindow.getAllWindows().forEach(win => {
                            if (!win.isDestroyed()) {
                                win.webContents.send(channel, payload);
                            }
                        });
                    };

                    if (response.event === 'stream.event' && response.data) {
                        const { stream_id, data: inner } = response.data;
                        if (inner && inner.type) {
                            if (inner.type === 'log') {
                                broadcast('logcat-output', { stream_id, ...inner.payload });
                            } else if (inner.type === 'started') {
                                broadcast('logcat-started', { stream_id, ...inner.payload });
                            } else if (inner.type === 'process_finished') {
                                broadcast('logcat-finished', { stream_id, ...inner.payload });
                            } else if (inner.type === 'error') {
                                broadcast('logcat-error', { stream_id, ...inner.payload });
                            } else {
                                broadcast(response.event, response.data);
                            }
                        } else {
                            broadcast(response.event, response.data);
                        }
                    } else {
                        broadcast(response.event, response.data);
                    }
                    return;
                }
                if (response && typeof response.id !== 'undefined' && requestCallbacks.has(response.id)) {
                    const { resolve, reject } = requestCallbacks.get(response.id);
                    if (response.error) {
                        reject(new Error(response.error.message));
                    } else {
                        resolve(response.result);
                    }
                    requestCallbacks.delete(response.id);
                }
            } catch (e) {
                console.error('Error parsing JSON from Python:', e);
            }
        });
    });

    ipcMain.handle('call-backend-api', async (event, request) => {
        return new Promise((resolve, reject) => {
            requestCallbacks.set(request.id, { resolve, reject });
            pythonProcess.stdin.write(JSON.stringify(request) + '\n');
        });
    });
}
