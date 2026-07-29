// ==================== 窗口相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const windowApi = {
  toggleDevTools: () => ipcInvoke(IPC_CHANNEL_NAMES.toggleDevTools),
  openDevTools: () => ipcInvoke(IPC_CHANNEL_NAMES.openDevTools),
  restart: () => ipcInvoke(IPC_CHANNEL_NAMES.restart),
  openExternal: (url: string) => ipcInvoke(IPC_CHANNEL_NAMES.openExternal, url),
};
