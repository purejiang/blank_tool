// ==================== 文件系统相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const fsApi = {
  getFileStats: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.getFileStats, filePath),
  openPath: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.openPath, filePath),
};
