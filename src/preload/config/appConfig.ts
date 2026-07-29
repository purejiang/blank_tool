// ==================== App 配置 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const appConfig = {
  get: (key: string) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getAppConfig, key),
  set: (key: string, value: unknown) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.setAppConfig, key, value),
  setMany: (updates: Record<string, unknown>) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.setManyAppConfig, updates),
  getAll: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getAllAppConfig),
  reset: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.resetAppConfig),
};

const onAppConfigChange = (callback: (key: string, value: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, key: string, value: unknown) => callback(key, value);
  ipcRenderer.on(IPC_CHANNEL_NAMES.appConfigChanged, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.appConfigChanged, handler);
};

export const appConfigApi = { appConfig, onAppConfigChange };
