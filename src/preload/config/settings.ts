// ==================== 设置相关 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const settings = {
  getViewModel: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getSettingsViewModel),
  resolvePaths: (paths: { runtime?: string; server?: string }) =>
    ipcRenderer.invoke(IPC_CHANNEL_NAMES.resolveSettingsPaths, paths),
};

export const settingsApi = { settings };
