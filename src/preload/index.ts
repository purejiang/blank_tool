import { contextBridge, ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../shared/ipc/channels';
import { ipcInvoke } from './core/ipcInvoke';
import { callBackendAPI, callBackendByRequest } from './core/callBackend';
import { toolApi } from './api/tool';
import { cacheApi } from './api/cache';
import { systemApi } from './api/system';
import { taskApi } from './api/task';
import { logsApi } from './api/logs';
import { appApi } from './api/app';
import { dialogApi } from './electron/dialog';
import { fsApi } from './electron/fs';
import { clipboardApi } from './electron/clipboard';
import { windowApi } from './electron/window';
import { appInfoApi } from './electron/appInfo';
import { rendererLogApi } from './electron/rendererLog';
import { appConfigApi } from './config/appConfig';
import { userConfigApi } from './config/userConfig';
import { settingsApi } from './config/settings';
import { deviceEventsApi } from './events/deviceEvents';
import { streamEventsApi } from './events/streamEvents';
import { updateEventsApi } from './events/updateEvents';
import { quitDialogApi } from './events/quitDialog';
// preload.js 运行在渲染进程中

// 预加载，暴露安全的API给渲染进程
const electronApi = {
  callBackendAPI,
  callBackendByRequest,
  // ==================== 后端API (extracted into src/preload/api/) ====================
  ...toolApi,
  ...cacheApi,
  ...systemApi,
  ...taskApi,
  ...logsApi,
  ...appApi,

  // ==================== electron API (extracted into src/preload/electron/) ====================
  ...dialogApi,
  ...fsApi,
  ...clipboardApi,
  ...windowApi,
  ...appInfoApi,
  ...rendererLogApi,

  // ==================== 配置 (extracted into src/preload/config/) ====================
  ...appConfigApi,
  ...userConfigApi,
  ...settingsApi,

  // ==================== 事件监听 (extracted into src/preload/events/) ====================
  ...deviceEventsApi,
  ...streamEventsApi,
  ...updateEventsApi,
  ...quitDialogApi,

  showSystemNotification: (title: string, body: string) => ipcInvoke(IPC_CHANNEL_NAMES.showSystemNotification, { title, body }),
};

contextBridge.exposeInMainWorld('electronAPI', electronApi);
