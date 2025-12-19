

/**
 * 缓存服务
 */
import unifiedAPI from '../api/unifiedAPI.js';

class CacheService {
    constructor() {
        this.cacheInfo = null;
    }

    async getCacheInfo(force = false) {
        if (this.cacheInfo && !force) {
            return this.cacheInfo;
        }

        try {
            const api = unifiedAPI.getAPI()
            if (api && typeof api.getCacheInfo === 'function') {
                this.cacheInfo = await api.getCacheInfo();
                return this.cacheInfo;
            }
            throw new Error('getCacheInfo API not implemented');
        } catch (error) {
            console.error('获取缓存信息失败:', error);
            // Return empty structure on error to prevent UI issues
            return {
                cache: { size: 0, files: 0 },
                output: { size: 0, files: 0 },
                total: { size: 0, files: 0 }
            };
        }
    }

    async clearCache() {
        try {
            const api = unifiedAPI.getAPI()
            if (api && typeof api.clearCache === 'function') {
                const result = await api.clearCache();
                this.cacheInfo = { size: 0, files: 0 }; // 清除后重置
                return { success: true, ...result };
            }
            throw new Error('clearCache API not implemented');
        } catch (error) {
            console.error('清除缓存失败:', error);
            return { success: false, error: error.message || '清除缓存失败' };
        }
    }

    async clearStorage(target = 'all') {
        try {
            const api = unifiedAPI.getAPI()
            if (api && typeof api.clearStorage === 'function') {
                const result = await api.clearStorage(target);
                // Force refresh cache info after clearing
                await this.getCacheInfo(true);
                return { success: true, ...result };
            }
            throw new Error('clearStorage API not implemented');
        } catch (error) {
            console.error('清除存储失败:', error);
            return { success: false, error: error.message || '清除存储失败' };
        }
    }
}

export default CacheService;