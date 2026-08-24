// ==================== 剪贴板相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

export const clipboardApi = {
  writeClipboardText: (text: string) => ipcInvoke(IPC_CHANNEL_NAMES.writeClipboardText, text),
};
