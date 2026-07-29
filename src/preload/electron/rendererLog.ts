// ==================== 渲染进程日志相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const rendererLogApi = {
  rendererLog: (level: 'error' | 'warn' | 'info', message: string) => ipcInvoke(IPC_CHANNEL_NAMES.rendererLog, level, message),
};
