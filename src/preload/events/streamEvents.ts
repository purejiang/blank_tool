// ==================== 流式事件 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const onStreamEvent = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.streamEvent, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.streamEvent, handler);
};

export const streamEventsApi = { onStreamEvent };
