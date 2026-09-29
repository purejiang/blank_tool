

/**
 * 缓存服务
 */
import { log } from '@utils/logger'
import unifiedApi from '../api/unifiedApi';

type CacheInfo = Record<string, unknown>;

class CacheService {
    private cacheInfo: CacheInfo | null;

    constructor() {
        this.cacheInfo = null;
    }

    async getCacheInfo(force = false) {
        if (this.cacheInfo && !force) {
            return this.cacheInfo;
        }

        try {
            const api = unifiedApi.getAPI()
            if (api && typeof api.getCacheInfo === 'function') {
                const raw: any = await api.getCacheInfo();
                // `callBackendAPI` resolves to a FAILURE ENVELOPE
                // ({success:false, error}) instead of throwing, and a backend
                // that is still starting up (or a handler error) produces it.
                // Assigning that to `cacheInfo` makes SettingsPage read
                // `.total.size` off undefined on the next render — the red toast
                // on the storage card. Only a payload actually shaped like
                // CacheInfo may be cached.
                if (!raw || typeof raw !== 'object' || !raw.total || typeof raw.total !== 'object') {
                    throw new Error(raw?.error || 'unexpected cache.info payload');
                }
                this.cacheInfo = raw;
                return this.cacheInfo;
            }
            throw new Error('getCacheInfo API not implemented');
        } catch (error) {
            log.error('获取缓存信息失败:', error);
            // Return empty structure on error to prevent UI issues
            return {
                tasks: { size: 0, files: 0 },
                output: { size: 0, files: 0 },
                logs: { size: 0, files: 0 },
                total: { size: 0, files: 0 }
            };
        }
    }

    async clearStorage(target = 'all') {
        try {
            const api = unifiedApi.getAPI()
            if (api && typeof api.clearStorage === 'function') {
                const result = await api.clearStorage(target);
                // Force refresh cache info after clearing
                await this.getCacheInfo(true);
                return { success: true, ...result };
            }
            throw new Error('clearStorage API not implemented');
        } catch (error) {
            log.error('清除存储失败:', error);
            return { success: false, error: error.message || '清除存储失败' };
        }
    }
}

export default CacheService;
