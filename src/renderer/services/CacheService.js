

/**
 * 缓存服务
 */
import unifiedAPI from '../api/unifiedApi.js';

class CacheService {
    constructor() {
        this.cacheInfo = null;
    }

    async getCacheInfo() {
        if (this.cacheInfo) {
            return this.cacheInfo;
        }

        try {
            this.cacheInfo = await unifiedAPI.call('cache.get_info');
            return this.cacheInfo;
        } catch (error) {
            console.error('获取缓存信息失败:', error);
            this.cacheInfo = null;
            return null;
        }
    }

    async clearCache() {
        try {
            await unifiedAPI.call('cache.clear');
            this.cacheInfo = { size: 0, files: 0 }; // 清除后重置
        } catch (error) {
            console.error('清除缓存失败:', error);
            throw error;
        }
    }
}

export default CacheService;