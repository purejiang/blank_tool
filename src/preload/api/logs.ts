// ==================== 日志相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const logsApi = {
  logsTail: (lines?: number) => callBackendAPI('logs.tail', { lines }),
};
