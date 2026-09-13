// ==================== 剪贴板相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const clipboardApi = {
  // The main-process handler returns `clipboard.readText()`, which is always a
  // string — narrow it here so the `ElectronApi` contract (Promise<string>)
  // holds instead of leaking `ipcInvoke`'s `unknown`.
  readClipboardText: async (): Promise<string> => {
    const text = await ipcInvoke(IPC_CHANNEL_NAMES.readClipboardText)
    return typeof text === 'string' ? text : ''
  },
  writeClipboardText: (text: string) => ipcInvoke(IPC_CHANNEL_NAMES.writeClipboardText, text),
};
