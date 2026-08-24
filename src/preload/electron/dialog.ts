// ==================== 对话框相关 ====================
import { ipcInvoke } from '../core/ipcInvoke';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';

type DialogOptions = {
  properties?: string[]
  [key: string]: unknown
}

export const dialogApi = {
  selectFile: (options: DialogOptions = {}) => {
    const props = Array.isArray(options.properties) ? [...options.properties] : []
    if (!props.includes('openFile')) props.push('openFile')
    const opts = { ...options, properties: props }
    return ipcInvoke(IPC_CHANNEL_NAMES.showOpenDialog, opts)
  },
  selectDirectory: (options: DialogOptions = {}) => {
    const props = Array.isArray(options.properties) ? [...options.properties] : []
    if (!props.includes('openDirectory')) props.push('openDirectory')
    const opts = { ...options, properties: props }
    return ipcInvoke(IPC_CHANNEL_NAMES.showOpenDialog, opts)
  },
};
