// ==================== 用户配置 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const userConfig = {
  get: (key: string) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getUserConfig, key),
  set: (key: string, value: unknown) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.setUserConfig, key, value),
  getAll: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getAllUserConfig),
  reset: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.resetUserConfig),
};

const onUserConfigChange = (callback: (key: string, value: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, key: string, value: unknown) => callback(key, value);
  ipcRenderer.on(IPC_CHANNEL_NAMES.userConfigChanged, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.userConfigChanged, handler);
};

export const userConfigApi = { userConfig, onUserConfigChange };
