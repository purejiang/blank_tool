import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

// Internal helper — NOT exposed on window.electronAPI. Use typed wrappers instead.
export const ipcInvoke = (channel: string, ...args: unknown[]): Promise<unknown> => {
  return ipcRenderer.invoke(channel, ...args);
};
