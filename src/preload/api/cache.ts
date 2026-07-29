// ==================== 缓存相关 ====================
import { callBackendAPI } from '../core/callBackend';

export const cacheApi = {
  getCacheInfo: () => callBackendAPI('cache.info'),
  // Legacy 'cache.clear' entry in ApiMethodMap has wrong param shape ({ target?: string }).
  // The real backend expects { cache_types, confirm } — string fallback preserves behavior.
  clearCache: (cacheTypes: unknown, confirm: unknown) =>
    callBackendAPI('cache.clear', { cache_types: cacheTypes, confirm }),
  clearOutput: () => callBackendAPI('output.clear'),
  clearStorage: (target?: string) => callBackendAPI('storage.clear', { target }),
};
