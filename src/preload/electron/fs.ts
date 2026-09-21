// ==================== 文件系统相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const fsApi = {
  getFileStats: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.getFileStats, filePath),
  openPath: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.openPath, filePath),
  writeTextFile: (path: string, content: string) => ipcInvoke(IPC_CHANNEL_NAMES.writeTextFile, { path, content }),
  readTextFile: (path: string, maxBytes?: number) => ipcInvoke(IPC_CHANNEL_NAMES.readTextFile, { path, maxBytes }),
};
