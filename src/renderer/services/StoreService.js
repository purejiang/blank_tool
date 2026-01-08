/**
 * 前端配置存储服务
 * 通过 app store 进行配置的获取、写入和重置操作
 * 不再直接调用 electronAPI，而是通过 store 作为中介层
 */

import { useAppConfigStore, useDeviceStore, initializeStores } from '../stores'

class ConfigStoreService {
    constructor() {
        this.appConfigStore = null
        this.userConfigStore = null
        this.deviceStore = null
    }

    /**
     * 初始化 store 实例
     */
   async initialize() {
        try {
            const stores = await initializeStores()
            this.deviceStore = stores.deviceStore
            this.appConfigStore = stores.appConfigStore
            this.userConfigStore = stores.userConfigStore
        } catch (error) {
            console.error('初始化 app config store、user config store 或 device store 失败:', error)
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

    /**
     * 确保 device store 实例可用
     */
    async ensureDeviceStore() {
        if (!this.deviceStore) {
            try {
                this.deviceStore = useDeviceStore()
            } catch (error) {
                throw new Error('无法获取 device store 实例')
            }
        }
        return this.deviceStore
    }

    /**
     * 获取设备配置（从 device store）
     */
    async getDeviceStore() {
        try {
            const store = await this.ensureDeviceStore()
            return store
        } catch (error) {
            console.error('获取 device config 失败:', error)
            throw error
        }
    }
    
    /**
     * 获取完整配置（从 app store）
     */
    async getAppConfigStore() {
        try {
            const store = await this.ensureAppConfigStore()
            return store
        } catch (error) {
            console.error('获取 app config 失败:', error)
            throw error
        }
    }

    /**
     * 获取扁平化配置
     */
    async getSettings() {
        try {
            const config = await this.getConfig()
            return this.flattenConfig(config)
        } catch (error) {
            console.error('获取扁平化配置失败:', error)
            return {}
        }
    }

    /**
     * 保存配置（通过 app store）
     */
    async saveSettings(settings) {
        try {
            const store = await this.ensureAppConfigStore()

            // 如果传入的是扁平化配置，需要转换为分组格式
            let configToSave = settings
            if (this.isFlattenedConfig(settings)) {
                configToSave = this.convertFlatToGroupedConfig(settings)
            }

            await store.saveConfig(configToSave)
            return { success: true }
        } catch (error) {
            console.error('保存配置失败:', error)
            throw error
        }
    }

    /**
     * 重置所有配置（通过 app store）
     */
    async resetSettings() {
        try {
            const store = await this.ensureAppConfigStore()
            await store.resetConfig()

            // 获取重置后的配置
            const settings = this.flattenConfig(store.config)
            return { success: true, settings }
        } catch (error) {
            console.error('重置配置失败:', error)
            throw error
        }
    }

    /**
     * 获取单个配置项（通过 app store）
     */
    async getSetting(key, defaultValue = null) {
        try {
            const store = await this.ensureAppConfigStore()
            return await store.getConfig(key, defaultValue)
        } catch (error) {
            console.error(`获取配置项 ${key} 失败:`, error)
            return defaultValue
        }
    }

    /**
     * 设置单个配置项（通过 app store）
     */
    async setSetting(key, value) {
        try {
            const store = await this.ensureAppConfigStore()
            await store.setConfig(key, value)
            return { success: true }
        } catch (error) {
            console.error(`设置配置项 ${key} 失败:`, error)
            throw error
        }
    }

    /**
     * 判断是否为扁平化配置
     */
    isFlattenedConfig(config) {
        // 检查是否包含点号分隔的键名
        return Object.keys(config).some(key => key.includes('.'))
    }

    /**
     * 将扁平化配置转换为分组配置
     */
    convertFlatToGroupedConfig(flatConfig) {
        const grouped = {}

        for (const [key, value] of Object.entries(flatConfig)) {
            const parts = key.split('.')
            let current = grouped

            // 导航到目标位置
            for (let i = 0; i < parts.length - 1; i++) {
                if (!current[parts[i]]) {
                    current[parts[i]] = {}
                }
                current = current[parts[i]]
            }

            // 设置值
            current[parts[parts.length - 1]] = value
        }

        return grouped
    }

    /**
     * 获取配置文件路径（通过 app store）
     */
    getConfigPath() {
        return 'app-store'
    }

    /**
     * 获取单个配置项的默认值
     */
    async getDefaultValue(key) {
        try {
            const store = await this.ensureAppConfigStore()
            // 从 store 的默认配置中获取
            const value = this.getNestedValue(store.defaultConfig || {}, key)
            return { success: true, value }
        } catch (error) {
            console.error(`获取配置项 ${key} 的默认值失败:`, error)
            throw error
        }
    }

    /**
     * 重置单个配置项
     */
    async resetSingleConfig(key) {
        try {
            const store = await this.ensureAppConfigStore()
            const defaultValue = this.getNestedValue(store.defaultConfig || {}, key)

            if (defaultValue !== undefined) {
                await store.setConfig(key, defaultValue)
            }

            const settings = await this.getSettings()
            return { success: true, settings }
        } catch (error) {
            console.error(`重置配置项 ${key} 失败:`, error)
            throw error
        }
    }

    /**
     * 扁平化配置对象
     */
    flattenConfig(config, prefix = '') {
        const flattened = {}

        for (const [key, value] of Object.entries(config)) {
            const newKey = prefix ? `${prefix}.${key}` : key

            if (value && typeof value === 'object' && !Array.isArray(value)) {
                Object.assign(flattened, this.flattenConfig(value, newKey))
            } else {
                flattened[newKey] = value
            }
        }

        return flattened
    }

    /**
     * 合并配置对象
     */
    mergeConfig(defaultConfig, savedConfig) {
        const result = { ...defaultConfig }

        for (const key in savedConfig) {
            if (savedConfig[key] && typeof savedConfig[key] === 'object' && !Array.isArray(savedConfig[key])) {
                result[key] = this.mergeConfig(result[key] || {}, savedConfig[key])
            } else {
                result[key] = savedConfig[key]
            }
        }

        return result
    }

    /**
     * 获取嵌套对象的值
     */
    getNestedValue(obj, path) {
        const keys = path.split('.')
        let current = obj

        for (const key of keys) {
            if (current && typeof current === 'object' && key in current) {
                current = current[key]
            } else {
                return undefined
            }
        }

        return current
    }

    /**
     * 设置嵌套对象的值
     */
    setNestedValue(obj, path, value) {
        const keys = path.split('.')
        let current = obj

        // 导航到目标位置
        for (let i = 0; i < keys.length - 1; i++) {
            if (!current[keys[i]] || typeof current[keys[i]] !== 'object') {
                current[keys[i]] = {}
            }
            current = current[keys[i]]
        }

        // 设置值
        current[keys[keys.length - 1]] = value
    }

    /**
     * 重置为默认配置（兼容方法）
     */
    async resetToDefault() {
        return await this.resetSettings()
    }

    /**
     * 获取 store 实例（供外部直接使用）
     */
    async getStore() {
        return await this.ensureAppConfigStore()
    }
}

export default ConfigStoreService