// ==================== 应用相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const appApi = {
  // 后端信息获取
  getBackendInfo: () => callBackendAPI('app.info'),
};
