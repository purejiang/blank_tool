/**
 * 前端配置存储服务
 * 通过 app store 进行配置的获取、写入和重置操作
 * 不再直接调用 electronAPI，而是通过 store 作为中介层
 */

import { log } from '@utils/logger'
import { useAppConfigStore, initializeStores } from '../stores'

class ConfigStoreService {
    private appConfigStore: ReturnType<typeof useAppConfigStore> | null = null

    /**
     * 初始化 store 实例
     */
    async initialize() {
        try {
            const stores = await initializeStores()
            this.appConfigStore = stores.appConfigStore
            log.debug('Store 服务初始化完成')
        } catch (error) {
            log.error('初始化 app config store 失败:', error)
        }
    }

    /**
     * 确保 app config store 实例可用
     */
    async ensureAppConfigStore() {
        if (!this.appConfigStore) {
            try {
                this.appConfigStore = useAppConfigStore()
            } catch (error) {
                throw new Error('无法获取 app config store 实例')
            }
        }
        return this.appConfigStore
    }
}

export default ConfigStoreService
