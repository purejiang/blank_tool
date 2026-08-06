// ==================== 缓存相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const cacheApi = {
  getCacheInfo: () => callBackendAPI('cache.info'),
  clearOutput: () => callBackendAPI('output.clear'),
  clearStorage: (target?: string) => callBackendAPI('storage.clear', { target }),
};
