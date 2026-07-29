// ==================== 系统相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const systemApi = {
  getSystemInfo: () => callBackendAPI('system.info'),
  getBackendBuildInfo: () => callBackendAPI('build.info'),
  // 'system.status' not in ApiMethodMap — string fallback.
  getStatus: () => callBackendAPI('system.status'),
};
