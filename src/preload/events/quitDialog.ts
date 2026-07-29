// ==================== 退出对话框 ====================
import { ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

const onQuitDialog = (callback: () => void) => {
  const handler = () => callback();
  ipcRenderer.on(IPC_CHANNEL_NAMES.showQuitDialog, handler);
  return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.showQuitDialog, handler);
};

const respondQuitDialog = (action: string) => {
  ipcRenderer.invoke(IPC_CHANNEL_NAMES.respondQuitDialog, action);
};

export const quitDialogApi = { onQuitDialog, respondQuitDialog };
