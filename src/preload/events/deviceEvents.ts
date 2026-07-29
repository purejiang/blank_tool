// ==================== 设备事件 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const onDeviceChange = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.deviceChange, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.deviceChange, handler);
};

const onLogcatOutput = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.logcatOutput, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatOutput, handler);
};

const onLogcatStarted = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.logcatStarted, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatStarted, handler);
};

const onLogcatFinished = (callback: (data: unknown) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: unknown) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.logcatFinished, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatFinished, handler);
};

const removeLogcatListener = () => {
  ipcRenderer.removeAllListeners(IPC_CHANNEL_NAMES.logcatOutput);
};

// Backend stderr tail (T23) — real-time traceback & crash dump
const onBackendStderrTail = (callback: (data: { lines: string[]; reason: string }) => void) => {
  const handler = (_event: Electron.IpcRendererEvent, data: { lines: string[]; reason: string }) => callback(data);
  ipcRenderer.on(IPC_CHANNEL_NAMES.backendStderrTail, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.backendStderrTail, handler);
};

export const deviceEventsApi = {
  onDeviceChange,
  onLogcatOutput,
  onLogcatStarted,
  onLogcatFinished,
  removeLogcatListener,
  onBackendStderrTail,
};
