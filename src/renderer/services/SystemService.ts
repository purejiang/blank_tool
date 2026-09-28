import unifiedApi from '../api/unifiedApi'
import { log } from '@utils/logger'

class SystemService {
    constructor() { }

    async getSystemInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getSystemInfo === 'function') {
            return await api.getSystemInfo()
        }
        throw new Error('getSystemInfo 方法未实现')
    }

    async getBackendBuildInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getBackendBuildInfo === 'function') {
            return await api.getBackendBuildInfo()
        }
        throw new Error('getBackendBuildInfo 方法未实现')
    }

    async getBuildInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getBuildInfo === 'function') {
            return await api.getBuildInfo()
        }
        throw new Error('getBuildInfo 方法未实现')
    }

    async getAppInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getAppInfo === 'function') {
            return await api.getAppInfo()
        }
        throw new Error('getAppInfo 方法未实现')
    }

    async getBackendInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getBackendInfo === 'function') {
            return await api.getBackendInfo()
        }
        throw new Error('getBackendInfo 方法未实现')
    }

    async getFontendBuildInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getFontendBuildInfo === 'function') {
            return await api.getFontendBuildInfo()
        }
        throw new Error('getFontendBuildInfo 方法未实现')
    }

    async selectDirectory(options = {}) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.selectDirectory === 'function') {
            return await api.selectDirectory(options)
        }
        throw new Error('selectDirectory 方法未实现')
    }

    async selectFile(options = {}) {
        // 优先使用自定义的 selectFile，如果不可用则回退到系统对话框
        const api = unifiedApi.getAPI()
        if (api && typeof api.selectFile === 'function') {
            return await api.selectFile(options)
        }
        throw new Error('selectFile 方法未实现')
    }

    async openPath(path) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.openPath === 'function') {
            return await api.openPath(path)
        }
        throw new Error('openPath 方法未实现')
    }

    async copyText(text) {
        if (!text) return false

        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text)
            return true
        }
        const api = unifiedApi.getAPI()
        if (api && typeof api.writeClipboardText === 'function') {
            return await api.writeClipboardText(text)
        }
        throw new Error('writeClipboardText 方法未实现')
    }

    async getFileStats(path) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getFileStats === 'function') {
            return await api.getFileStats(path)
        }
        throw new Error('getFileStats 方法未实现')
    }

    // ---- 文件读写通道（WP1 主进程通道；工作流导出 / 描述符导入用） ----

    /** 「另存为」对话框；返回 { canceled, filePath? }。 */
    async showSave(options = {}) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.showSave === 'function') {
            return await api.showSave(options)
        }
        throw new Error('showSave 方法未实现')
    }

    /** 写文本文件（UTF-8）；返回 { success, error? }。 */
    async writeTextFile(path: string, content: string) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.writeTextFile === 'function') {
            return await api.writeTextFile(path, content)
        }
        throw new Error('writeTextFile 方法未实现')
    }

    /** 读文本文件（可带上限）；返回 { success, content?, error? }。 */
    async readTextFile(path: string, maxBytes?: number) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.readTextFile === 'function') {
            return await api.readTextFile(path, maxBytes)
        }
        throw new Error('readTextFile 方法未实现')
    }
}

export default SystemService
