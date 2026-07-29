// ==================== 下载相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const downloadApi = {
  downloadFile: (url: string, filename?: string, taskId?: string) =>
    callBackendAPI('download.file', { url, filename, task_id: taskId }),
};
