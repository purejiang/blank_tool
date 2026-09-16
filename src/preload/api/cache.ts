// ==================== 缓存相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const cacheApi = {
  // `force` bypasses the backend's short size-walk memo (see cache_handler):
  // the settings page passes it for an explicit user refresh.
  getCacheInfo: (force = false) => callBackendAPI('cache.info', { force }),
  clearOutput: () => callBackendAPI('output.clear'),
  clearStorage: (target?: string) => callBackendAPI('storage.clear', { target }),
};
