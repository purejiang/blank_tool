// ==================== 文件系统相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const fsApi = {
  getFileStats: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.getFileStats, filePath),
  writeFile: (filePath: string, content: string) => ipcInvoke(IPC_CHANNEL_NAMES.writeFile, filePath, content),
  readFile: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.readFile, filePath),
  readImageAsDataURL: (filePath: string) => ipcInvoke(IPC_CHANNEL_NAMES.readImageAsDataURL, filePath),
  // opts.reveal === false → 用系统默认程序真正打开文件（如 .html 报告进浏览器）；
  // 缺省保持历史行为：目录 openPath，文件 showItemInFolder（资源管理器中显示）
  openPath: (filePath: string, opts?: { reveal?: boolean }) =>
    ipcInvoke(IPC_CHANNEL_NAMES.openPath, filePath, opts ?? null),
};
