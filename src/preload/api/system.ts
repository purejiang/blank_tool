// ==================== 系统相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const systemApi = {
  getSystemInfo: () => callBackendAPI('system.info'),
  getBackendBuildInfo: () => callBackendAPI('build.info'),
};
