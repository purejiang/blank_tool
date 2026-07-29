// ==================== 更新事件 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import { ipcInvoke } from '../core/ipcInvoke';

// Invokers (renderer → main)
const checkForUpdates = () => ipcInvoke(IPC_CHANNEL_NAMES.checkForUpdates);
const downloadUpdate = () => ipcInvoke(IPC_CHANNEL_NAMES.downloadUpdate);
const quitAndInstall = () => ipcInvoke(IPC_CHANNEL_NAMES.quitAndInstall);

// Listeners (main → renderer)
const onUpdateAvailable = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.updateAvailable, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateAvailable, handler);
};

const onUpdateNotAvailable = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.updateNotAvailable, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateNotAvailable, handler);
};

const onDownloadProgress = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.downloadProgress, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.downloadProgress, handler);
};

const onUpdateDownloaded = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.updateDownloaded, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateDownloaded, handler);
};

const onUpdateError = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.updateError, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.updateError, handler);
};

export const updateEventsApi = {
  checkForUpdates,
  downloadUpdate,
  quitAndInstall,
  onUpdateAvailable,
  onUpdateNotAvailable,
  onDownloadProgress,
  onUpdateDownloaded,
  onUpdateError,
};
