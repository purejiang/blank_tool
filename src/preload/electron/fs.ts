// ==================== 文件系统相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const fsApi = {
  getFileStats: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.getFileStats, filePath),
  writeFile: (filePath: string, content: string) => ipcInvoke(IPC_CHANNEL_NAMES.writeFile, filePath, content),
  readFile: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.readFile, filePath),
  openPath: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.openPath, filePath),
};
