// ==================== 应用信息相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const appInfoApi = {
  resolvePath: (pathStr: string) => ipcInvoke(IPC_CHANNEL_NAMES.pathResolve, pathStr),
  getAppInfo: () => ipcInvoke(IPC_CHANNEL_NAMES.getAppInfo),
  getFontendBuildInfo: () => ipcInvoke(IPC_CHANNEL_NAMES.getFontendBuildInfo),
  getBackendHealth: () => ipcInvoke(IPC_CHANNEL_NAMES.getBackendHealth),
  readElectronLogTail: (lines?: number) => ipcInvoke(IPC_CHANNEL_NAMES.readElectronLogTail, { lines }),
};
